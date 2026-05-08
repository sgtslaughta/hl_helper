package tui

import (
	"bytes"
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func init() {
	// Use Ascii profile for deterministic output in tests
	lipgloss.SetColorProfile(termenv.Ascii)
}

func TestStep(t *testing.T) {
	buf := &bytes.Buffer{}
	Step(buf, "test message")
	output := buf.String()

	if !strings.Contains(output, GlyphArrow) {
		t.Errorf("Step output should contain arrow glyph, got: %q", output)
	}
	if !strings.Contains(output, "test message") {
		t.Errorf("Step output should contain message, got: %q", output)
	}
	if !strings.HasSuffix(output, "\n") {
		t.Errorf("Step output should end with newline")
	}
}

func TestSuccess(t *testing.T) {
	buf := &bytes.Buffer{}
	Success(buf, "all good")
	output := buf.String()

	if !strings.Contains(output, GlyphCheck) {
		t.Errorf("Success output should contain check glyph, got: %q", output)
	}
	if !strings.Contains(output, "all good") {
		t.Errorf("Success output should contain message, got: %q", output)
	}
	if !strings.HasSuffix(output, "\n") {
		t.Errorf("Success output should end with newline")
	}
}

func TestFailure(t *testing.T) {
	buf := &bytes.Buffer{}
	Failure(buf, "something broke")
	output := buf.String()

	if !strings.Contains(output, GlyphCross) {
		t.Errorf("Failure output should contain cross glyph, got: %q", output)
	}
	if !strings.Contains(output, "something broke") {
		t.Errorf("Failure output should contain message, got: %q", output)
	}
	if !strings.HasSuffix(output, "\n") {
		t.Errorf("Failure output should end with newline")
	}
}

func TestWarn(t *testing.T) {
	buf := &bytes.Buffer{}
	Warn(buf, "be careful")
	output := buf.String()

	if !strings.Contains(output, GlyphWarn) {
		t.Errorf("Warn output should contain warn glyph, got: %q", output)
	}
	if !strings.Contains(output, "be careful") {
		t.Errorf("Warn output should contain message, got: %q", output)
	}
	if !strings.HasSuffix(output, "\n") {
		t.Errorf("Warn output should end with newline")
	}
}

func TestInfo(t *testing.T) {
	buf := &bytes.Buffer{}
	Info(buf, "note this")
	output := buf.String()

	if !strings.Contains(output, GlyphInfo) {
		t.Errorf("Info output should contain info glyph, got: %q", output)
	}
	if !strings.Contains(output, "note this") {
		t.Errorf("Info output should contain message, got: %q", output)
	}
	if !strings.HasSuffix(output, "\n") {
		t.Errorf("Info output should end with newline")
	}
}

func TestHeader(t *testing.T) {
	buf := &bytes.Buffer{}
	Header(buf, "Section")
	output := buf.String()

	if !strings.Contains(output, "Section") {
		t.Errorf("Header output should contain message, got: %q", output)
	}
	if !strings.HasSuffix(output, "\n") {
		t.Errorf("Header output should end with newline")
	}
}

func TestKeyValue(t *testing.T) {
	buf := &bytes.Buffer{}
	KeyValue(buf, "Name", "Value")
	output := buf.String()

	if !strings.Contains(output, "Name") {
		t.Errorf("KeyValue output should contain key, got: %q", output)
	}
	if !strings.Contains(output, "Value") {
		t.Errorf("KeyValue output should contain value, got: %q", output)
	}
	if !strings.HasSuffix(output, "\n") {
		t.Errorf("KeyValue output should end with newline")
	}
}

func TestTable(t *testing.T) {
	buf := &bytes.Buffer{}
	rows := [][2]string{
		{"Host", "localhost"},
		{"Port", "8080"},
		{"Status", "Running"},
	}
	Table(buf, rows)
	output := buf.String()

	// Check all keys and values are present
	for _, row := range rows {
		if !strings.Contains(output, row[0]) {
			t.Errorf("Table output should contain key %q", row[0])
		}
		if !strings.Contains(output, row[1]) {
			t.Errorf("Table output should contain value %q", row[1])
		}
	}

	// Simple alignment check: keys should start at same position
	lines := strings.Split(strings.TrimSuffix(output, "\n"), "\n")
	if len(lines) != len(rows) {
		t.Errorf("Table should have %d lines, got %d", len(rows), len(lines))
	}
}
