package outbox_test

import (
	"bytes"
	"path/filepath"
	"sync"
	"testing"

	bolt "go.etcd.io/bbolt"

	"github.com/hlhelper/hl-agent/internal/outbox"
)

func testMasterKey() []byte {
	key := make([]byte, 32)
	copy(key, "test-master-key-32-bytes-long!")
	return key
}

func testPayload(n int) []byte {
	return bytes.Repeat([]byte{byte(n)}, 100+n*10)
}

func TestAppendDrainOrdered(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	const n = 5
	ids := make([]uint64, n)
	for i := 0; i < n; i++ {
		id, err := ob.Append(testPayload(i))
		if err != nil {
			t.Fatalf("Append %d: %v", i, err)
		}
		ids[i] = id
	}

	entries, err := ob.Peek(10)
	if err != nil {
		t.Fatalf("Peek: %v", err)
	}

	if len(entries) != n {
		t.Fatalf("Peek returned %d entries, want %d", len(entries), n)
	}

	for i := 0; i < n; i++ {
		if entries[i].ID != ids[i] {
			t.Errorf("entry %d ID = %d, want %d", i, entries[i].ID, ids[i])
		}
		if !bytes.Equal(entries[i].Payload, testPayload(i)) {
			t.Errorf("entry %d payload mismatch", i)
		}
	}
}

func TestAppendReturnsMonotonicIDs(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	const n = 10
	var prev uint64
	for i := 0; i < n; i++ {
		id, err := ob.Append(testPayload(i))
		if err != nil {
			t.Fatalf("Append %d: %v", i, err)
		}
		if id <= prev {
			t.Errorf("ID %d not > %d", id, prev)
		}
		prev = id
	}
}

func TestPersistenceAcrossReopen(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	// First session: append
	ob1, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open 1: %v", err)
	}

	const n = 3
	ids := make([]uint64, n)
	for i := 0; i < n; i++ {
		id, err := ob1.Append(testPayload(i))
		if err != nil {
			t.Fatalf("Append %d: %v", i, err)
		}
		ids[i] = id
	}
	ob1.Close()

	// Second session: reopen and verify
	ob2, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open 2: %v", err)
	}
	defer ob2.Close()

	entries, err := ob2.Peek(10)
	if err != nil {
		t.Fatalf("Peek: %v", err)
	}

	if len(entries) != n {
		t.Fatalf("Peek returned %d entries, want %d", len(entries), n)
	}

	for i := 0; i < n; i++ {
		if entries[i].ID != ids[i] {
			t.Errorf("entry %d ID = %d, want %d", i, entries[i].ID, ids[i])
		}
		if !bytes.Equal(entries[i].Payload, testPayload(i)) {
			t.Errorf("entry %d payload mismatch", i)
		}
	}
}

func TestAckRemovesEntry(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	id, err := ob.Append(testPayload(0))
	if err != nil {
		t.Fatalf("Append: %v", err)
	}

	err = ob.Ack(id)
	if err != nil {
		t.Fatalf("Ack: %v", err)
	}

	entries, err := ob.Peek(10)
	if err != nil {
		t.Fatalf("Peek: %v", err)
	}

	if len(entries) != 0 {
		t.Errorf("Peek returned %d entries, want 0", len(entries))
	}

	len_, err := ob.Len()
	if err != nil {
		t.Fatalf("Len: %v", err)
	}
	if len_ != 0 {
		t.Errorf("Len = %d, want 0", len_)
	}
}

func TestAckUnknownIDIsNoop(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	// Ack on empty outbox should not error
	err = ob.Ack(99999)
	if err != nil {
		t.Fatalf("Ack on unknown ID: %v", err)
	}
}

func TestCapDropsOldestByCount(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 3,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	const n = 5
	ids := make([]uint64, n)
	for i := 0; i < n; i++ {
		id, err := ob.Append(testPayload(i))
		if err != nil {
			t.Fatalf("Append %d: %v", i, err)
		}
		ids[i] = id
	}

	len_, err := ob.Len()
	if err != nil {
		t.Fatalf("Len: %v", err)
	}
	if len_ != 3 {
		t.Fatalf("Len = %d, want 3", len_)
	}

	entries, err := ob.Peek(10)
	if err != nil {
		t.Fatalf("Peek: %v", err)
	}

	if len(entries) != 3 {
		t.Fatalf("Peek returned %d entries, want 3", len(entries))
	}

	// Should have ids 2, 3, 4 (0, 1 dropped)
	for i := 0; i < 3; i++ {
		if entries[i].ID != ids[2+i] {
			t.Errorf("entry %d ID = %d, want %d", i, entries[i].ID, ids[2+i])
		}
	}
}

func TestCapDropsOldestByBytes(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	// Each testPayload(i) is 100+i*10 bytes.
	// testPayload(0) = 100 bytes, testPayload(1) = 110 bytes, testPayload(2) = 120 bytes
	// With MaxBytes=210, we can fit testPayload(0) + testPayload(1) but not all 3.
	// After appending testPayload(2), oldest is pruned.
	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   300, // Enough for ~2 entries with encryption overhead
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	const n = 3
	ids := make([]uint64, n)
	for i := 0; i < n; i++ {
		id, err := ob.Append(testPayload(i))
		if err != nil {
			t.Fatalf("Append %d: %v", i, err)
		}
		ids[i] = id
	}

	len_, err := ob.Len()
	if err != nil {
		t.Fatalf("Len: %v", err)
	}

	// Should have fewer than 3 entries
	if len_ >= 3 {
		t.Fatalf("Len = %d, want < 3 due to cap", len_)
	}
}

func TestEncryptionAtRest(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}

	plaintext := []byte("top-secret-stuff-XYZ")
	_, err = ob.Append(plaintext)
	if err != nil {
		t.Fatalf("Append: %v", err)
	}

	ob.Close()

	// Open raw bbolt and check that plaintext is not in the file
	rawdb, err := bolt.Open(path, 0600, nil)
	if err != nil {
		t.Fatalf("bolt.Open: %v", err)
	}
	defer rawdb.Close()

	err = rawdb.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("outbox"))
		if b == nil {
			t.Fatal("bucket not found")
		}
		return b.ForEach(func(k, v []byte) error {
			if bytes.Contains(v, plaintext) {
				t.Errorf("plaintext found in stored value!")
			}
			return nil
		})
	})
	if err != nil {
		t.Fatalf("ForEach: %v", err)
	}
}

func TestVerifyPassesCleanState(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	for i := 0; i < 5; i++ {
		_, err := ob.Append(testPayload(i))
		if err != nil {
			t.Fatalf("Append %d: %v", i, err)
		}
	}

	err = ob.Verify()
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
}

func TestVerifyDetectsTamperedCiphertext(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}

	_, err = ob.Append(testPayload(0))
	if err != nil {
		t.Fatalf("Append: %v", err)
	}

	ob.Close()

	// Tamper with the stored ciphertext
	rawdb, err := bolt.Open(path, 0600, nil)
	if err != nil {
		t.Fatalf("bolt.Open: %v", err)
	}

	err = rawdb.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("outbox"))
		if b == nil {
			return nil
		}
		return b.ForEach(func(k, v []byte) error {
			if len(v) > 0 {
				// Flip a bit in the middle
				tampered := make([]byte, len(v))
				copy(tampered, v)
				tampered[len(tampered)/2] ^= 0xFF
				return b.Put(k, tampered)
			}
			return nil
		})
	})
	if err != nil {
		t.Fatalf("tampering: %v", err)
	}
	rawdb.Close()

	// Reopen and verify should fail
	ob2, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open 2: %v", err)
	}
	defer ob2.Close()

	err = ob2.Verify()
	if err == nil {
		t.Fatal("Verify should have failed on tampered data")
	}
}

func TestVerifyDetectsTamperedPrevHash(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}

	id, err := ob.Append(testPayload(0))
	if err != nil {
		t.Fatalf("Append: %v", err)
	}

	ob.Close()

	// Tamper with the prev hash metadata
	rawdb, err := bolt.Open(path, 0600, nil)
	if err != nil {
		t.Fatalf("bolt.Open: %v", err)
	}

	var idBytes [8]byte
	// Assuming id == 1, build the meta key
	for i := 0; i < 8; i++ {
		idBytes[i] = byte(id >> (56 - i*8))
	}

	err = rawdb.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("meta"))
		if b == nil {
			return nil
		}
		metaKey := append([]byte("prev:"), idBytes[:]...)
		hash := b.Get(metaKey)
		if hash != nil && len(hash) == 32 {
			tampered := make([]byte, 32)
			copy(tampered, hash)
			tampered[0] ^= 0xFF
			return b.Put(metaKey, tampered)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("tampering: %v", err)
	}
	rawdb.Close()

	// Reopen and verify should fail
	ob2, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open 2: %v", err)
	}
	defer ob2.Close()

	err = ob2.Verify()
	if err == nil {
		t.Fatal("Verify should have failed on tampered prev hash")
	}
}

func TestOpenRejectsBadKeyLength(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	_, err := outbox.Open(path, outbox.Options{
		MasterKey:  []byte("short-key"),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err == nil {
		t.Fatal("Open should reject short key")
	}
}

func TestDifferentMasterKeyCannotDecrypt(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	key1 := make([]byte, 32)
	copy(key1, "first-master-key-32-bytes-long!")

	key2 := make([]byte, 32)
	copy(key2, "second-master-key-32bytes-longx")

	// Append with key1
	ob1, err := outbox.Open(path, outbox.Options{
		MasterKey:  key1,
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open 1: %v", err)
	}

	_, err = ob1.Append(testPayload(0))
	if err != nil {
		t.Fatalf("Append: %v", err)
	}

	ob1.Close()

	// Try to open with key2 and access the data
	ob2, err := outbox.Open(path, outbox.Options{
		MasterKey:  key2,
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open 2: %v", err)
	}
	defer ob2.Close()

	// Peek should fail due to decryption error
	_, err = ob2.Peek(10)
	if err == nil {
		t.Fatal("Peek should fail with wrong key")
	}
}

func TestLenZeroOnFresh(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 30,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	len_, err := ob.Len()
	if err != nil {
		t.Fatalf("Len: %v", err)
	}

	if len_ != 0 {
		t.Errorf("Len = %d, want 0", len_)
	}
}

func TestConcurrentAppendIsSerialized(t *testing.T) {
	tmpdir := t.TempDir()
	path := filepath.Join(tmpdir, "outbox.db")

	ob, err := outbox.Open(path, outbox.Options{
		MasterKey:  testMasterKey(),
		MaxBytes:   1 << 31,
		MaxEntries: 1000,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer ob.Close()

	const nGoroutines = 50
	var wg sync.WaitGroup
	idChan := make(chan uint64, nGoroutines)

	for i := 0; i < nGoroutines; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			id, err := ob.Append(testPayload(index % 10))
			if err != nil {
				t.Errorf("Append: %v", err)
			}
			idChan <- id
		}(i)
	}

	wg.Wait()
	close(idChan)

	// Collect all IDs
	ids := make(map[uint64]bool)
	for id := range idChan {
		ids[id] = true
	}

	if len(ids) != nGoroutines {
		t.Errorf("Got %d unique IDs, want %d", len(ids), nGoroutines)
	}

	len_, err := ob.Len()
	if err != nil {
		t.Fatalf("Len: %v", err)
	}

	if len_ != nGoroutines {
		t.Errorf("Len = %d, want %d", len_, nGoroutines)
	}
}
