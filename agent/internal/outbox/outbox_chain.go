package outbox

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"io"

	"golang.org/x/crypto/hkdf"
)

// entryDigest computes sha256(id_be || blob).
func entryDigest(id uint64, blob []byte) []byte {
	h := sha256.New()
	keyBuf := make([]byte, 8)
	binary.BigEndian.PutUint64(keyBuf, id)
	h.Write(keyBuf)
	h.Write(blob)
	return h.Sum(nil)
}

// computeChainTip computes sha256(id_be || blob || prevChainTip).
func computeChainTip(id uint64, blob []byte, prevChainTip []byte) []byte {
	h := sha256.New()
	keyBuf := make([]byte, 8)
	binary.BigEndian.PutUint64(keyBuf, id)
	h.Write(keyBuf)
	h.Write(blob)
	h.Write(prevChainTip)
	return h.Sum(nil)
}

func buildAEAD(master []byte) (cipher.AEAD, error) {
	h := hkdf.New(sha256.New, master, nil, []byte("hl-agent/outbox/v1"))
	key := make([]byte, 32)
	if _, err := io.ReadFull(h, key); err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	return cipher.NewGCM(block)
}

// encryptEntry encrypts a payload with AAD = id_be || prev_hash.
// Returns nonce || ciphertext.
func encryptEntry(aead cipher.AEAD, id uint64, prevHash, payload []byte) ([]byte, error) {
	nonce := make([]byte, nonceLen)
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}

	// AAD = id_be || prev_hash
	aad := make([]byte, 8+32)
	binary.BigEndian.PutUint64(aad[:8], id)
	copy(aad[8:], prevHash)

	ciphertext := aead.Seal(nil, nonce, payload, aad)

	// Return nonce || ciphertext
	return append(nonce, ciphertext...), nil
}

// decryptEntry decrypts a blob given id and prev_hash as AAD.
func decryptEntry(aead cipher.AEAD, id uint64, prevHash, blob []byte) ([]byte, error) {
	if len(blob) < nonceLen {
		return nil, fmt.Errorf("outbox: blob too short")
	}

	nonce := blob[:nonceLen]
	ciphertext := blob[nonceLen:]

	// AAD = id_be || prev_hash
	aad := make([]byte, 8+32)
	binary.BigEndian.PutUint64(aad[:8], id)
	copy(aad[8:], prevHash)

	plaintext, err := aead.Open(nil, nonce, ciphertext, aad)
	if err != nil {
		return nil, ErrChainBroken
	}

	return plaintext, nil
}
