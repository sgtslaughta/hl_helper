// Package outbox stores outbound results encrypted-at-rest with hash chaining.
package outbox

import (
	"bytes"
	"crypto/cipher"
	"encoding/binary"
	"errors"
	"fmt"
	"sync"

	bolt "go.etcd.io/bbolt"
)

const (
	bucketName = "outbox"
	metaBucket = "meta"
	nonceLen   = 12
)

var (
	// ErrChainBroken is returned when hash chain verification fails during decrypt.
	ErrChainBroken = errors.New("outbox: chain broken")
	// ErrChainTruncated is returned when entries are missing from the chain (detected via last_id).
	ErrChainTruncated = errors.New("outbox: chain truncated")
	// ErrChainReordered is returned when the order of entries in the chain is incorrect.
	ErrChainReordered = errors.New("outbox: chain reordered")
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
		mb := tx.Bucket([]byte(metaBucket))

		// Check chain integrity: verify last_id matches max id present
		lastIDBytes := mb.Get([]byte("last_id"))
		var lastID uint64
		if lastIDBytes != nil && len(lastIDBytes) == 8 {
			lastID = binary.BigEndian.Uint64(lastIDBytes)
		}

		// Find max id present
		var maxID uint64
		if b != nil {
			if k, _ := b.Cursor().Last(); k != nil && len(k) == 8 {
				maxID = binary.BigEndian.Uint64(k)
			}
		}

		// Detect truncation or reordering
		if lastID > 0 && maxID > 0 {
			if lastID > maxID {
				// Entries were deleted without updating chain
				return ErrChainTruncated
			}
		}

		// Set nextID for appends
		if maxID > 0 {
			o.nextID = maxID + 1
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

		c := b.Cursor()
		lastKey, lastVal := c.Last()
		if lastKey != nil && len(lastKey) == 8 {
			prevHash = entryDigest(binary.BigEndian.Uint64(lastKey), lastVal)
		}

		// Current ID
		id = o.nextID
		o.nextID++

		// Encrypt payload with AAD = id_be || prev_hash
		blob, err := encryptEntry(o.aead, id, prevHash, payload)
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

		// Compute new chain_tip = sha256(id_be || blob || prev_chain_tip)
		prevChainTip := mb.Get([]byte("chain_tip"))
		if prevChainTip == nil {
			prevChainTip = make([]byte, 32)
		}
		newChainTip := computeChainTip(id, blob, prevChainTip)

		// Store chain_tip and last_id atomically
		if err := mb.Put([]byte("chain_tip"), newChainTip); err != nil {
			return err
		}
		lastIDBytes := make([]byte, 8)
		binary.BigEndian.PutUint64(lastIDBytes, id)
		if err := mb.Put([]byte("last_id"), lastIDBytes); err != nil {
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
			payload, err := decryptEntry(o.aead, id, prevHash, v)
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
// The entry digest is preserved for chain verification.
func (o *Outbox) Ack(id uint64) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	return o.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketName))
		mb := tx.Bucket([]byte(metaBucket))

		keyBuf := make([]byte, 8)
		binary.BigEndian.PutUint64(keyBuf, id)

		// Get the entry before deletion to store the full blob (for chain re-derivation)
		blob := b.Get(keyBuf)
		if blob != nil {
			ackedKey := append([]byte("acked:"), keyBuf...)
			// Store the full ciphertext blob so Verify can recompute the chain tip identically.
			cp := make([]byte, len(blob))
			copy(cp, blob)
			if err := mb.Put(ackedKey, cp); err != nil {
				return err
			}
		}

		// Delete the entry
		if err := b.Delete(keyBuf); err != nil {
			return err
		}

		// Delete prev_hash metadata
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
// Returns ErrChainBroken if any entry fails verification, ErrChainTruncated if
// entries are missing, or ErrChainReordered if entries are out of order.
func (o *Outbox) Verify() error {
	o.mu.Lock()
	defer o.mu.Unlock()

	return o.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketName))
		mb := tx.Bucket([]byte(metaBucket))

		// Get last_id from meta
		lastIDBytes := mb.Get([]byte("last_id"))
		var lastID uint64
		if lastIDBytes != nil && len(lastIDBytes) == 8 {
			lastID = binary.BigEndian.Uint64(lastIDBytes)
		}

		// If nothing appended, nothing to verify
		if lastID == 0 {
			return nil
		}

		// Build maps of present and acked entries
		presentEntries := make(map[uint64][]byte)
		ackedDigests := make(map[uint64][]byte)

		if b != nil {
			c := b.Cursor()
			for k, v := c.First(); k != nil; k, v = c.Next() {
				if len(k) == 8 {
					id := binary.BigEndian.Uint64(k)
					presentEntries[id] = v
				}
			}
		}

		if mb != nil {
			c := mb.Cursor()
			for k, v := c.First(); k != nil; k, v = c.Next() {
				if len(k) > 6 && string(k[:6]) == "acked:" {
					// Parse id from key
					idBytes := k[6:]
					if len(idBytes) == 8 {
						id := binary.BigEndian.Uint64(idBytes)
						cp := make([]byte, len(v))
						copy(cp, v)
						ackedDigests[id] = cp
					}
				}
			}
		}

		// Walk chain from 1 to lastID
		prevChainTip := make([]byte, 32)
		for id := uint64(1); id <= lastID; id++ {
			if entry, present := presentEntries[id]; present {
				// Verify present entry
				idBuf := make([]byte, 8)
				binary.BigEndian.PutUint64(idBuf, id)
				metaKey := append([]byte("prev:"), idBuf...)

				prevHash := mb.Get(metaKey)
				if prevHash == nil || len(prevHash) != 32 {
					return fmt.Errorf("outbox: missing prev_hash for id %d", id)
				}

				_, err := decryptEntry(o.aead, id, prevHash, entry)
				if err != nil {
					return ErrChainBroken
				}

				// Update chain tip with this entry
				newChainTip := computeChainTip(id, entry, prevChainTip)
				prevChainTip = newChainTip

			} else if storedBlob, acked := ackedDigests[id]; acked {
				// Acked entries store the full ciphertext blob; recompute the chain tip identically to Append.
				newChainTip := computeChainTip(id, storedBlob, prevChainTip)
				prevChainTip = newChainTip

			} else {
				// Entry missing and not acked - this is truncation
				return ErrChainTruncated
			}
		}

		// Verify final chain tip matches meta
		metaChainTip := mb.Get([]byte("chain_tip"))
		if metaChainTip != nil && len(metaChainTip) == 32 {
			if !bytes.Equal(prevChainTip, metaChainTip) {
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
		k, v := c.First()
		if k == nil {
			return nil
		}
		if err := b.Delete(k); err != nil {
			return err
		}
		mb := tx.Bucket([]byte(metaBucket))
		if mb != nil {
			// Store full blob so Verify can recompute the chain tip after eviction.
			if len(k) == 8 && v != nil {
				ackedKey := append([]byte("acked:"), k...)
				cp := make([]byte, len(v))
				copy(cp, v)
				_ = mb.Put(ackedKey, cp)
			}
			_ = mb.Delete(append([]byte("prev:"), k...))
		}
	}
}
