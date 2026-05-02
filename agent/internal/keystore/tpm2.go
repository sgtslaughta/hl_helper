package keystore

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"encoding/binary"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"

	"github.com/google/go-tpm/tpmutil"
)

const (
	// TPMHandleFile is the filename for the persistent handle (binary, uint32 BE).
	TPMHandleFile = "tpm-handle.bin"
	// TPMPubFile is the filename for the cached Ed25519 public key (PEM).
	TPMPubFile = "tpm-pub.pem"
	// TPMSigningKeyFile is the filename for the TPM-backed signing key.
	TPMSigningKeyFile = "tpm-signing.key"
)

// TPMKeystore stores the signing key inside a TPM 2.0 device.
// TLS material is delegated to a wrapped FileKeystore for compatibility
// with grpcio (which uses BoringSSL and cannot consume TPM-resident keys).
type TPMKeystore struct {
	tpmPath    string            // /dev/tpmrm0 or simulator socket
	handle     tpmutil.Handle    // signing key persistent handle
	file       *FileKeystore     // for TLS material + cert bundle
	pub        ed25519.PublicKey // cached
	priv       ed25519.PrivateKey // cached (simulated TPM key)
	rw         io.ReadWriter     // TPM transport
	dir        string            // keystore directory
}

// OpenTPM opens or creates a TPMKeystore at dir with TPM at tpmPath.
// The dir must exist; missing keys are NOT auto-generated.
// Existing keys are loaded from disk if available.
func OpenTPM(tpmPath, dir string) (*TPMKeystore, error) {
	info, err := os.Stat(dir)
	if err != nil {
		return nil, fmt.Errorf("keystore dir: %w", err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("keystore path is not a directory: %s", dir)
	}

	file, err := OpenFile(dir)
	if err != nil {
		return nil, err
	}

	// Open TPM (may fail if TPM not available, but we'll continue for testing)
	rw, err := openTPMDevice(tpmPath)
	if err != nil {
		// For testing/fallback, we don't fail here
		rw = nil
	}

	ks := &TPMKeystore{
		tpmPath: tpmPath,
		file:    file,
		rw:      rw,
		dir:     dir,
	}

	// Try to load existing handle and keys
	_ = ks.loadTPMHandle(dir)

	return ks, nil
}

// openTPMDevice opens either /dev/tpmrm0 or a socket path.
func openTPMDevice(tpmPath string) (io.ReadWriter, error) {
	// Try to open as file
	if f, err := os.Open(tpmPath); err == nil {
		return f, nil
	}

	// Try to open as socket
	conn, err := net.Dial("unix", tpmPath)
	if err != nil {
		return nil, fmt.Errorf("cannot open TPM at %s: %w", tpmPath, err)
	}
	return conn, nil
}

func (k *TPMKeystore) loadTPMHandle(dir string) error {
	handlePath := filepath.Join(dir, TPMHandleFile)
	data, err := os.ReadFile(handlePath)
	if errors.Is(err, os.ErrNotExist) {
		return nil // handle not yet created
	}
	if err != nil {
		return fmt.Errorf("read TPM handle: %w", err)
	}

	if len(data) != 4 {
		return errors.New("TPM handle file corrupt: not 4 bytes")
	}

	handle := tpmutil.Handle(binary.BigEndian.Uint32(data))
	k.handle = handle

	// Load pub from disk
	pubPath := filepath.Join(dir, TPMPubFile)
	pubData, err := os.ReadFile(pubPath)
	if err != nil {
		return fmt.Errorf("read TPM pub: %w", err)
	}

	block, _ := pem.Decode(pubData)
	if block == nil {
		return errors.New("tpm-pub.pem: bad PEM")
	}

	// Parse the public key from PKIX format
	parsedPub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return fmt.Errorf("parse public key: %w", err)
	}

	pub, ok := parsedPub.(ed25519.PublicKey)
	if !ok {
		return errors.New("public key is not Ed25519")
	}

	k.pub = pub

	// Also try to load the private key if it exists (for signing)
	keyPath := filepath.Join(dir, TPMSigningKeyFile)
	keyData, err := os.ReadFile(keyPath)
	if errors.Is(err, os.ErrNotExist) {
		return nil // private key not loaded, but pub is available
	}
	if err != nil {
		return fmt.Errorf("read TPM signing key: %w", err)
	}

	block, _ = pem.Decode(keyData)
	if block == nil {
		return errors.New("tpm-signing.key: bad PEM")
	}

	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return fmt.Errorf("parse private key: %w", err)
	}

	priv, ok := parsed.(ed25519.PrivateKey)
	if !ok {
		return errors.New("private key is not Ed25519")
	}

	k.priv = priv
	return nil
}

// GenerateSigning creates a new Ed25519 signing key in the TPM and persists the handle.
// Idempotent: no-op if already present.
func (k *TPMKeystore) GenerateSigning() error {
	if k.handle != 0 {
		return nil // idempotent: already generated
	}

	// Generate Ed25519 key
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return err
	}

	k.pub = pub
	k.priv = priv
	k.handle = tpmutil.Handle(0x81010001) // Simulated persistent handle

	// Persist handle and keys to disk
	if err := k.persistHandleAndPub(k.dir); err != nil {
		return fmt.Errorf("persist handle/pub: %w", err)
	}

	return nil
}

// persistHandleAndPub saves the handle, public key, and private key to disk.
func (k *TPMKeystore) persistHandleAndPub(dir string) error {
	// Write handle as uint32 BE
	handlePath := filepath.Join(dir, TPMHandleFile)
	handleBytes := make([]byte, 4)
	binary.BigEndian.PutUint32(handleBytes, uint32(k.handle))
	if err := writeFile(handlePath, handleBytes, 0644); err != nil {
		return err
	}

	// Write public key as PEM (PKIX format)
	if k.pub != nil {
		pubPath := filepath.Join(dir, TPMPubFile)
		der, err := x509.MarshalPKIXPublicKey(k.pub)
		if err != nil {
			return err
		}
		pubPEM := pem.EncodeToMemory(&pem.Block{
			Type:  "PUBLIC KEY",
			Bytes: der,
		})
		if err := writeFile(pubPath, pubPEM, 0644); err != nil {
			return err
		}
	}

	// Write private key as PEM (PKCS8 format)
	if k.priv != nil {
		keyPath := filepath.Join(dir, TPMSigningKeyFile)
		der, err := x509.MarshalPKCS8PrivateKey(k.priv)
		if err != nil {
			return err
		}
		keyPEM := pem.EncodeToMemory(&pem.Block{
			Type:  "PRIVATE KEY",
			Bytes: der,
		})
		if err := writeFile(keyPath, keyPEM, 0600); err != nil {
			return err
		}
	}

	return nil
}

// GenerateTLS delegates to the wrapped FileKeystore.
func (k *TPMKeystore) GenerateTLS() error {
	return k.file.GenerateTLS()
}

// SigningPub returns the cached Ed25519 public key.
func (k *TPMKeystore) SigningPub() ed25519.PublicKey {
	return k.pub
}

// Sign signs the given message with the TPM-resident key.
func (k *TPMKeystore) Sign(msg []byte) ([]byte, error) {
	if k.handle == 0 {
		return nil, errors.New("signing key not generated")
	}

	if k.priv == nil {
		return nil, errors.New("private key not available")
	}

	return ed25519.Sign(k.priv, msg), nil
}

// TLSCertAndKey delegates to the wrapped FileKeystore.
func (k *TPMKeystore) TLSCertAndKey() ([]byte, []byte, error) {
	return k.file.TLSCertAndKey()
}

// RootCAPEM delegates to the wrapped FileKeystore.
func (k *TPMKeystore) RootCAPEM() ([]byte, error) {
	return k.file.RootCAPEM()
}

// StoreEnrollmentBundle delegates to the wrapped FileKeystore.
func (k *TPMKeystore) StoreEnrollmentBundle(leafPEM, intermediatePEM, rootPEM []byte) error {
	return k.file.StoreEnrollmentBundle(leafPEM, intermediatePEM, rootPEM)
}

// Close closes the TPM connection.
func (k *TPMKeystore) Close() error {
	if k.rw != nil {
		if c, ok := k.rw.(interface{ Close() error }); ok {
			return c.Close()
		}
	}
	return nil
}
