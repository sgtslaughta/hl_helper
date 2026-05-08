package tui

import (
	"fmt"
	"io"
	"strings"
)

// Step writes a step message with arrow glyph.
func Step(w io.Writer, msg string) {
	line := fmt.Sprintf("%s %s", GlyphArrow, msg)
	fmt.Fprintln(w, line)
}

// Success writes a success message with check glyph.
func Success(w io.Writer, msg string) {
	line := StyleSuccess.Render(fmt.Sprintf("%s %s", GlyphCheck, msg))
	fmt.Fprintln(w, line)
}

// Failure writes a failure message with cross glyph.
func Failure(w io.Writer, msg string) {
	line := StyleFailure.Render(fmt.Sprintf("%s %s", GlyphCross, msg))
	fmt.Fprintln(w, line)
}

// Warn writes a warning message with warn glyph.
func Warn(w io.Writer, msg string) {
	line := StyleWarn.Render(fmt.Sprintf("%s %s", GlyphWarn, msg))
	fmt.Fprintln(w, line)
}

// Info writes an info message with info glyph.
func Info(w io.Writer, msg string) {
	line := StyleAccent.Render(fmt.Sprintf("%s %s", GlyphInfo, msg))
	fmt.Fprintln(w, line)
}

// Header writes a styled header line.
func Header(w io.Writer, msg string) {
	line := StyleHeader.Render(msg)
	fmt.Fprintln(w, line)
}

// KeyValue writes a key-value pair with bold key.
func KeyValue(w io.Writer, key, val string) {
	k := StyleKey.Render(key)
	line := fmt.Sprintf("%s: %s", k, val)
	fmt.Fprintln(w, line)
}

// Table writes a 2-column key-value table with aligned keys.
func Table(w io.Writer, rows [][2]string) {
	if len(rows) == 0 {
		return
	}

	// Find max key length for alignment
	maxLen := 0
	for _, row := range rows {
		if len(row[0]) > maxLen {
			maxLen = len(row[0])
		}
	}

	for _, row := range rows {
		k := StyleKey.Render(row[0])
		// Pad key to align values
		padding := strings.Repeat(" ", maxLen-len(row[0]))
		line := fmt.Sprintf("%s%s: %s", k, padding, row[1])
		fmt.Fprintln(w, line)
	}
}
