package tui

import (
	"fmt"
	"io"
)

// RunSpinner runs fn while showing a spinner with msg. On completion: success or failure line.
// If stdout is not a TTY, falls back to plain "→ msg... done" or "→ msg... FAILED: err".
// For simplicity, always uses non-TTY path (prints start line, runs fn, prints result line).
func RunSpinner(w io.Writer, msg string, fn func() error) error {
	// Print step start
	Step(w, msg)

	// Run the function
	err := fn()

	// Print result
	if err == nil {
		line := fmt.Sprintf("%s done", GlyphCheck)
		fmt.Fprintln(w, line)
	} else {
		line := fmt.Sprintf("%s FAILED: %v", GlyphCross, err)
		fmt.Fprintln(w, line)
	}

	return err
}
