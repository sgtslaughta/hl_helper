package tui

import (
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func TestGlyphs(t *testing.T) {
	glyphs := map[string]string{
		"Check":   GlyphCheck,
		"Cross":   GlyphCross,
		"Arrow":   GlyphArrow,
		"Bullet":  GlyphBullet,
		"Spinner": GlyphSpinner,
		"Info":    GlyphInfo,
		"Warn":    GlyphWarn,
	}

	for name, glyph := range glyphs {
		if glyph == "" {
			t.Errorf("Glyph %s is empty", name)
		}
	}
}

func TestStylesRender(t *testing.T) {
	lipgloss.SetColorProfile(termenv.TrueColor)

	styles := map[string]lipgloss.Style{
		"StyleHeader":  StyleHeader,
		"StyleSuccess": StyleSuccess,
		"StyleFailure": StyleFailure,
		"StyleWarn":    StyleWarn,
		"StyleMuted":   StyleMuted,
		"StyleAccent":  StyleAccent,
		"StyleKey":     StyleKey,
	}

	testMsg := "test"
	for name, style := range styles {
		rendered := style.Render(testMsg)
		if rendered == "" {
			t.Errorf("Style %s rendered empty", name)
		}
		// When TrueColor is forced, styles should contain ANSI codes
		if rendered != testMsg && !containsANSI(rendered) {
			t.Errorf("Style %s should contain ANSI codes when rendered with TrueColor", name)
		}
	}
}

func containsANSI(s string) bool {
	return len(s) > 0 && s[0] == '\x1b'
}
