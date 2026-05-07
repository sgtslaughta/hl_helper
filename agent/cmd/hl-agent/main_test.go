package main

import (
	"os"
	"testing"
)

func TestBootCounterPath(t *testing.T) {
	dir := "/tmp/test"
	expected := "/tmp/test/bootcount"
	if got := bootCounterPath(dir); got != expected {
		t.Errorf("expected %q, got %q", expected, got)
	}
}

func TestReadBootCounter(t *testing.T) {
	tmpdir := t.TempDir()

	// Non-existent file returns 0
	if count := readBootCounter(tmpdir); count != 0 {
		t.Errorf("expected 0 for non-existent file, got %d", count)
	}

	// Write a counter and read it back
	counterPath := bootCounterPath(tmpdir)
	if err := os.WriteFile(counterPath, []byte("5"), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if count := readBootCounter(tmpdir); count != 5 {
		t.Errorf("expected 5, got %d", count)
	}
}

func TestIncrementBootCounter(t *testing.T) {
	tmpdir := t.TempDir()

	// First increment: 0 -> 1
	incrementBootCounter(tmpdir)
	if count := readBootCounter(tmpdir); count != 1 {
		t.Errorf("expected 1 after first increment, got %d", count)
	}

	// Second increment: 1 -> 2
	incrementBootCounter(tmpdir)
	if count := readBootCounter(tmpdir); count != 2 {
		t.Errorf("expected 2 after second increment, got %d", count)
	}
}

func TestClearBootCounter(t *testing.T) {
	tmpdir := t.TempDir()

	// Write a counter
	counterPath := bootCounterPath(tmpdir)
	if err := os.WriteFile(counterPath, []byte("3"), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	// Verify it exists
	if _, err := os.Stat(counterPath); err != nil {
		t.Fatalf("counter file should exist: %v", err)
	}

	// Clear it
	clearBootCounter(tmpdir)

	// Verify it's gone
	if _, err := os.Stat(counterPath); !os.IsNotExist(err) {
		t.Errorf("counter file should be removed")
	}

	// Clearing again should not error
	clearBootCounter(tmpdir)
}
