// Package outbox stores outbound results encrypted-at-rest with hash chaining.
package outbox

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"sync"

	bolt "go.etcd.io/bbolt"
	"golang.org/x/crypto/hkdf"
)

const (
	bucketName = "outbox"
	metaBucket = "meta"
	nonceLen   = 12
)

var (
	// ErrChainBroken is returned when hash chain verification fails during decrypt.
	ErrChainBroken = errors.New("outbox: chain broken")
	// ErrBadKey is returned when the master key length is not 32 bytes.
	ErrBadKey = errors.New("outbox: bad master key")
)

// Entry represents a single encrypted message in the outbox with its sequence ID.
type Entry struct {
	ID      uint64
	Payload []byte
}

// Options holds configuration for Outbox initialization.
type Options struct {
	// MasterKey is the 32-byte key for AES-256-GCM encryption.
	MasterKey []byte
	// MaxBytes is the maximum total size in bytes; oldest entries are evicted when exceeded.
	MaxBytes int64
	// MaxEntries is the maximum number of entries; oldest are evicted when exceeded.
	MaxEntries int
}

// Outbox stores encrypted messages with hash-chain integrity verification.
// All entries are encrypted at rest with AES-256-GCM and verified on read.
type Outbox struct {
	mu     sync.Mutex
	db     *bolt.DB
	aead   cipher.AEAD
	opts   Options
	nextID uint64
}

// Open creates or opens an Outbox at the given BoltDB file path.
// The master key in opts must be exactly 32 bytes. Returns ErrBadKey if not.
func Open(path string, opts Options) (*Outbox, error) {
	if len(opts.MasterKey) != 32 {
		return nil, ErrBadKey
	}

	db, err := bolt.Open(path, 0600, nil)
	if err != nil {
		return nil, err
	}

	aead, err := buildAEAD(opts.MasterKey)
	if err != nil {
		db.Close()
		return nil, err
	}

	ob := &Outbox{
		db:   db,
		aead: aead,
		opts: opts,
	}

	if err := ob.init(); err != nil {
		db.Close()
		return nil, err
	}

	return ob, nil
}

func (o *Outbox) init() error {
	return o.db.Update(func(tx *bolt.Tx) error {
		if _, err := tx.CreateBucketIfNotExists([]byte(bucketName)); err != nil {
			return err
		}
		if _, err := tx.CreateBucketIfNotExists([]byte(metaBucket)); err != nil {
			return err
		}
		b := tx.Bucket([]byte(bucketName))
		if b != nil {
			if k, _ := b.Cursor().Last(); k != nil && len(k) == 8 {
				o.nextID = binary.BigEndian.Uint64(k) + 1
			}
		}
		if o.nextID == 0 {
			o.nextID = 1
		}
		return nil
	})
}

// Append adds a message to the outbox, encrypts it, and returns its sequence ID.
// Returns an error if encryption fails.
func (o *Outbox) Append(payload []byte) (uint64, error) {
	o.mu.Lock()
	defer o.mu.Unlock()

	var id uint64
	err := o.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketName))
		mb := tx.Bucket([]byte(metaBucket))

		// Get the previous hash (genesis or from last entry)
		prevHash := make([]byte, 32)
		var lastID uint64

		c := b.Cursor()
		lastKey, lastVal := c.Last()
		if lastKey != nil && len(lastKey) == 8 {
			lastID = binary.BigEndian.Uint64(lastKey)
			prevHash = entryDigest(lastID, lastVal)
		}

		// Current ID
		id = o.nextID
		o.nextID++

		// Encrypt payload with AAD = id_be || prev_hash
		blob, err := o.encryptEntry(id, prevHash, payload)
		if err != nil {
			return err
		}

		// Store encrypted blob
		keyBuf := make([]byte, 8)
		binary.BigEndian.PutUint64(keyBuf, id)
		if err := b.Put(keyBuf, blob); err != nil {
			return err
		}

		// Store prev_hash in meta bucket
		metaKey := append([]byte("prev:"), keyBuf...)
		if err := mb.Put(metaKey, prevHash); err != nil {
			return err
		}

		// Enforce cap inline
		return o.enforceCapTx(tx)
	})
	if err != nil {
		return 0, err
	}

	return id, nil
}

// Peek returns up to n entries from the outbox without removing them.
// Entries are decrypted and verified; returns an error if chain is broken.
func (o *Outbox) Peek(n int) ([]Entry, error) {
	o.mu.Lock()
	defer o.mu.Unlock()

	var entries []Entry
	err := o.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketName))
		if b == nil {
			return nil
		}
		mb := tx.Bucket([]byte(metaBucket))
		c := b.Cursor()
		count := 0
		for k, v := c.First(); k != nil && count < n; k, v = c.Next() {
			if len(k) != 8 {
				continue
			}
			id := binary.BigEndian.Uint64(k)
			metaKey := append([]byte("prev:"), k...)
			prevHash := mb.Get(metaKey)
			if prevHash == nil || len(prevHash) != 32 {
				return fmt.Errorf("outbox: missing prev_hash for id %d", id)
			}
			payload, err := o.decryptEntry(id, prevHash, v)
			if err != nil {
				return err
			}
			entries = append(entries, Entry{ID: id, Payload: payload})
			count++
		}
		return nil
	})
	return entries, err
}

// Ack removes an entry from the outbox by ID after it has been processed.
func (o *Outbox) Ack(id uint64) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	return o.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketName))
		keyBuf := make([]byte, 8)
		binary.BigEndian.PutUint64(keyBuf, id)
		if err := b.Delete(keyBuf); err != nil {
			return err
		}
		mb := tx.Bucket([]byte(metaBucket))
		metaKey := append([]byte("prev:"), keyBuf...)
		return mb.Delete(metaKey)
	})
}

// Len returns the current number of entries in the outbox.
func (o *Outbox) Len() (int, error) {
	o.mu.Lock()
	defer o.mu.Unlock()

	var count int
	err := o.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketName))
		if b == nil {
			return nil
		}
		count = b.Stats().KeyN
		return nil
	})
	return count, err
}

// Verify decrypts and verifies all entries in the outbox against the hash chain.
// Returns ErrChainBroken if any entry fails verification.
func (o *Outbox) Verify() error {
	o.mu.Lock()
	defer o.mu.Unlock()

	return o.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketName))
		if b == nil {
			return nil
		}
		mb := tx.Bucket([]byte(metaBucket))
		c := b.Cursor()
		for k, v := c.First(); k != nil; k, v = c.Next() {
			if len(k) != 8 {
				continue
			}
			id := binary.BigEndian.Uint64(k)
			metaKey := append([]byte("prev:"), k...)
			prevHash := mb.Get(metaKey)
			if prevHash == nil || len(prevHash) != 32 {
				return fmt.Errorf("outbox: missing prev_hash for id %d", id)
			}
			_, err := o.decryptEntry(id, prevHash, v)
			if err != nil {
				return ErrChainBroken
			}
		}
		return nil
	})
}

// Close closes the underlying BoltDB and releases resources.
func (o *Outbox) Close() error {
	return o.db.Close()
}

// --- helpers ---

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

func (o *Outbox) encryptEntry(id uint64, prevHash, payload []byte) ([]byte, error) {
	nonce := make([]byte, nonceLen)
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}

	// AAD = id_be || prev_hash
	aad := make([]byte, 8+32)
	binary.BigEndian.PutUint64(aad[:8], id)
	copy(aad[8:], prevHash)

	ciphertext := o.aead.Seal(nil, nonce, payload, aad)

	// Return nonce || ciphertext
	return append(nonce, ciphertext...), nil
}

func (o *Outbox) decryptEntry(id uint64, prevHash, blob []byte) ([]byte, error) {
	if len(blob) < nonceLen {
		return nil, fmt.Errorf("outbox: blob too short")
	}

	nonce := blob[:nonceLen]
	ciphertext := blob[nonceLen:]

	// AAD = id_be || prev_hash
	aad := make([]byte, 8+32)
	binary.BigEndian.PutUint64(aad[:8], id)
	copy(aad[8:], prevHash)

	plaintext, err := o.aead.Open(nil, nonce, ciphertext, aad)
	if err != nil {
		return nil, ErrChainBroken
	}

	return plaintext, nil
}

func entryDigest(id uint64, blob []byte) []byte {
	h := sha256.New()
	keyBuf := make([]byte, 8)
	binary.BigEndian.PutUint64(keyBuf, id)
	h.Write(keyBuf)
	h.Write(blob)
	return h.Sum(nil)
}

func (o *Outbox) enforceCapTx(tx *bolt.Tx) error {
	b := tx.Bucket([]byte(bucketName))
	if b == nil {
		return nil
	}
	for {
		var count int
		var size int64
		c := b.Cursor()
		for k, v := c.First(); k != nil; k, v = c.Next() {
			count++
			size += int64(len(v))
		}
		if count <= o.opts.MaxEntries && size <= o.opts.MaxBytes {
			return nil
		}
		c = b.Cursor()
		k, _ := c.First()
		if k == nil {
			return nil
		}
		if err := b.Delete(k); err != nil {
			return err
		}
		mb := tx.Bucket([]byte(metaBucket))
		if mb != nil {
			_ = mb.Delete(append([]byte("prev:"), k...))
		}
	}
}
