package terminal

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func TestRecorderHeaderAndFrames(t *testing.T) {
	var buf bytes.Buffer
	r, err := NewRecorder(&buf, 80, 24)
	if err != nil {
		t.Fatal(err)
	}
	if err := r.Write("o", []byte("hi")); err != nil {
		t.Fatal(err)
	}
	if err := r.Write("i", []byte("ls")); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(buf.String()), "\n")
	if len(lines) != 3 {
		t.Fatalf("expected header+2 frames, got %d", len(lines))
	}
	var hdr map[string]any
	if err := json.Unmarshal([]byte(lines[0]), &hdr); err != nil {
		t.Fatal(err)
	}
	if hdr["version"].(float64) != 2 || hdr["width"].(float64) != 80 {
		t.Fatalf("bad header: %v", hdr)
	}
	var row []any
	if err := json.Unmarshal([]byte(lines[1]), &row); err != nil {
		t.Fatal(err)
	}
	if row[1].(string) != "o" || row[2].(string) != "hi" {
		t.Fatalf("bad row: %v", row)
	}
}
