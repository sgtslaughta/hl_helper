package tui

import "github.com/charmbracelet/lipgloss"

// Colors
const (
	ColorPrimary = "#7c3aed"
	ColorSuccess = "#22c55e"
	ColorWarning = "#f59e0b"
	ColorDanger  = "#ef4444"
	ColorMuted   = "#6b7280"
	ColorAccent  = "#06b6d4"
)

// Glyphs
const (
	GlyphCheck   = "✓"
	GlyphCross   = "✗"
	GlyphArrow   = "→"
	GlyphBullet  = "•"
	GlyphSpinner = "⠋"
	GlyphInfo    = "ℹ"
	GlyphWarn    = "⚠"
)

// Styles
var (
	StyleHeader = lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color(ColorPrimary)).
		BorderBottom(true).
		BorderStyle(lipgloss.NormalBorder())

	StyleSuccess = lipgloss.NewStyle().
		Foreground(lipgloss.Color(ColorSuccess)).
		Bold(true)

	StyleFailure = lipgloss.NewStyle().
		Foreground(lipgloss.Color(ColorDanger)).
		Bold(true)

	StyleWarn = lipgloss.NewStyle().
		Foreground(lipgloss.Color(ColorWarning))

	StyleMuted = lipgloss.NewStyle().
		Foreground(lipgloss.Color(ColorMuted))

	StyleAccent = lipgloss.NewStyle().
		Foreground(lipgloss.Color(ColorAccent))

	StyleKey = lipgloss.NewStyle().
		Bold(true)
)
