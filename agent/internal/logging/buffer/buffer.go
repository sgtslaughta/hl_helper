// Package buffer provides a BoltDB-backed FIFO ring for agent log events.
package buffer

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"os"
	"sync"
	"time"

	bolt "go.etcd.io/bbolt"

	"github.com/hlhelper/hl-agent/internal/logging"
)

var (
	entriesBucket = []byte("entries")
	metaBucket    = []byte("meta")
	keyAck        = []byte("ack")
	keyDropped    = []byte("dropped")
)

// Options controls buffer eviction policy.
type Options struct {
	MaxBytes int64
	MaxAge   time.Duration
}

// Buffer is a BoltDB-backed FIFO ring buffer for agent log events.
type Buffer struct {
	db        *bolt.DB
	opt       Options
	mu        sync.Mutex
	corrupted bool
}

// Open opens or creates a buffer at path with the given options.
// If the database is corrupted, it is rotated to <path>.corrupt.<ts>
// and a fresh database is created.
func Open(path string, opt Options) (*Buffer, error) {
	db, err := bolt.Open(path, 0600, &bolt.Options{Timeout: 2 * time.Second})
	if err != nil {
		// DB is likely corrupted; rotate and retry
		ts := time.Now().UTC().Format("20060102T150405Z")
		if rerr := os.Rename(path, fmt.Sprintf("%s.corrupt.%s", path, ts)); rerr != nil && !os.IsNotExist(rerr) {
			return nil, fmt.Errorf("rotate corrupt buffer: %w", rerr)
		}
		db2, err2 := bolt.Open(path, 0600, &bolt.Options{Timeout: 2 * time.Second})
		if err2 != nil {
			return nil, err2
		}
		b := &Buffer{db: db2, opt: opt, corrupted: true}
		return b, b.initBuckets()
	}
	b := &Buffer{db: db, opt: opt}
	return b, b.initBuckets()
}

func (b *Buffer) initBuckets() error {
	return b.db.Update(func(tx *bolt.Tx) error {
		if _, err := tx.CreateBucketIfNotExists(entriesBucket); err != nil {
			return err
		}
		_, err := tx.CreateBucketIfNotExists(metaBucket)
		return err
	})
}

// Close closes the underlying database.
func (b *Buffer) Close() error {
	return b.db.Close()
}

// WasCorrupted reports whether the buffer recovered from a corruption.
func (b *Buffer) WasCorrupted() bool {
	return b.corrupted
}

func seqKey(seq uint64) []byte {
	k := make([]byte, 8)
	binary.BigEndian.PutUint64(k, seq)
	return k
}

// Append adds an event to the buffer.
// The event's Sequence field is used as the key.
// Eviction is performed if age or size limits are exceeded.
func (b *Buffer) Append(ev logging.Event) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	blob, err := json.Marshal(ev)
	if err != nil {
		return err
	}
	if err := b.db.Update(func(tx *bolt.Tx) error {
		return tx.Bucket(entriesBucket).Put(seqKey(ev.Event.Sequence), blob)
	}); err != nil {
		return err
	}
	return b.evictIfNeeded()
}

// PeekFrom returns events starting from the first key strictly greater than fromSeq,
// up to limit entries. If fromSeq is 0, starts from the beginning.
func (b *Buffer) PeekFrom(fromSeq uint64, limit int) ([]logging.Event, error) {
	out := make([]logging.Event, 0, limit)
	err := b.db.View(func(tx *bolt.Tx) error {
		c := tx.Bucket(entriesBucket).Cursor()
		var k, v []byte
		if fromSeq == 0 {
			k, v = c.First()
		} else {
			// seek to first key > fromSeq
			k, v = c.Seek(seqKey(fromSeq + 1))
		}
		for ; k != nil && len(out) < limit; k, v = c.Next() {
			var ev logging.Event
			if err := json.Unmarshal(v, &ev); err != nil {
				return err
			}
			out = append(out, ev)
		}
		return nil
	})
	return out, err
}

// Ack marks all entries with seq <= throughSeq as acknowledged and deletes them.
func (b *Buffer) Ack(throughSeq uint64) error {
	return b.db.Update(func(tx *bolt.Tx) error {
		bkt := tx.Bucket(entriesBucket)
		c := bkt.Cursor()
		for k, _ := c.First(); k != nil; k, _ = c.Next() {
			if binary.BigEndian.Uint64(k) > throughSeq {
				break
			}
			if err := bkt.Delete(k); err != nil {
				return err
			}
		}
		return tx.Bucket(metaBucket).Put(keyAck, seqKey(throughSeq))
	})
}

// Count returns the current number of entries in the buffer.
func (b *Buffer) Count() int {
	var n int
	_ = b.db.View(func(tx *bolt.Tx) error {
		n = tx.Bucket(entriesBucket).Stats().KeyN
		return nil
	})
	return n
}

// DroppedCount returns the total count of evicted entries.
func (b *Buffer) DroppedCount() uint64 {
	var n uint64
	_ = b.db.View(func(tx *bolt.Tx) error {
		v := tx.Bucket(metaBucket).Get(keyDropped)
		if len(v) == 8 {
			n = binary.BigEndian.Uint64(v)
		}
		return nil
	})
	return n
}

func (b *Buffer) bumpDropped(tx *bolt.Tx, n uint64) {
	var cur uint64
	if v := tx.Bucket(metaBucket).Get(keyDropped); len(v) == 8 {
		cur = binary.BigEndian.Uint64(v)
	}
	buf := make([]byte, 8)
	binary.BigEndian.PutUint64(buf, cur+n)
	_ = tx.Bucket(metaBucket).Put(keyDropped, buf)
}

func (b *Buffer) evictIfNeeded() error {
	return b.db.Update(func(tx *bolt.Tx) error {
		bkt := tx.Bucket(entriesBucket)
		// age-based eviction
		cur := bkt.Cursor()
		deadline := time.Now().Add(-b.opt.MaxAge)
		for {
			k, v := cur.First()
			if k == nil {
				break
			}
			var ev logging.Event
			if err := json.Unmarshal(v, &ev); err == nil && ev.TS.Before(deadline) {
				if err := bkt.Delete(k); err != nil {
					return err
				}
				b.bumpDropped(tx, 1)
				continue
			}
			break
		}
		// size-based eviction
		for tx.Size() > b.opt.MaxBytes {
			k, _ := bkt.Cursor().First()
			if k == nil {
				break
			}
			if err := bkt.Delete(k); err != nil {
				return err
			}
			b.bumpDropped(tx, 1)
		}
		return nil
	})
}
