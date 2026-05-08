package tui

import (
	"context"
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// DashboardSnapshot is the data the dashboard displays. Caller produces it.
type DashboardSnapshot struct {
	ServiceState string
	HostID       string
	GrpcEndpoint string
	AgentVersion string
	Hostname     string
	OS, OSVersion, Arch string
	CertNotAfter time.Time
	Sleeping     bool
	SleepUntil   time.Time
	LastUpdated  time.Time
	Err          string // non-empty if last refresh errored
}

// tickMsg is sent on each refresh interval tick.
type tickMsg time.Time

// model holds the dashboard state for Bubble Tea.
type model struct {
	fetch      func() DashboardSnapshot
	snapshot   DashboardSnapshot
	lastUpdate time.Time
	err        error
}

// Init returns the initial command.
func (m model) Init() tea.Cmd {
	return tea.Batch(
		tea.Tick(2*time.Second, func(t time.Time) tea.Msg { return tickMsg(t) }),
	)
}

// Update handles messages.
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
		}
	case tickMsg:
		m.snapshot = m.fetch()
		m.lastUpdate = time.Now()
		return m, tea.Tick(2*time.Second, func(t time.Time) tea.Msg { return tickMsg(t) })
	}
	return m, nil
}

// View renders the dashboard.
func (m model) View() string {
	return render(m.snapshot)
}

// render returns the rendered dashboard string for a snapshot.
func render(s DashboardSnapshot) string {
	// Service state line with color indicator
	var stateIndicator, stateColor string
	switch s.ServiceState {
	case "running":
		stateIndicator = "●"
		stateColor = ColorSuccess
	case "stopped":
		stateIndicator = "●"
		stateColor = ColorDanger
	default:
		stateIndicator = "●"
		stateColor = ColorWarning
	}
	stateStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(stateColor))
	serviceLine := fmt.Sprintf("Service: %s %-20s %s",
		stateStyle.Render(stateIndicator+" "+s.ServiceState),
		"",
		s.AgentVersion,
	)

	// Host line
	hostLine := fmt.Sprintf("Host:    %s (%s/%s)", s.Hostname, s.OS, s.Arch)

	// ID line
	idLine := fmt.Sprintf("ID:      %s", s.HostID)

	// Server line
	serverLine := fmt.Sprintf("Server:  %s", s.GrpcEndpoint)

	// Cert line with warning/error colors
	certLine := renderCertLine(s.CertNotAfter)

	// State line (awake vs sleeping)
	var stateLine string
	if s.Sleeping {
		sleepStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(ColorWarning))
		stateLine = "State:   " + sleepStyle.Render(fmt.Sprintf("sleeping until %s",
			s.SleepUntil.Format("2006-01-02 15:04 MST")))
	} else {
		awakeStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(ColorSuccess))
		stateLine = "State:   " + awakeStyle.Render("awake")
	}

	// Build content lines
	content := []string{
		serviceLine,
		hostLine,
		idLine,
		serverLine,
		certLine,
		stateLine,
	}

	// Add error if present
	if s.Err != "" {
		errorStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(ColorDanger))
		content = append(content, "Error:   "+errorStyle.Render(s.Err))
	}

	contentStr := strings.Join(content, "\n")

	// Render box
	boxStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color(ColorPrimary)).
		Padding(1, 2)

	// Header in the box
	headerStr := StyleHeader.Render("HL-AGENT STATUS")
	boxContent := headerStr + "\n" + contentStr

	box := boxStyle.Render(boxContent)

	// Footer with refresh indicator
	timeSinceRefresh := formatTimeSince(s.LastUpdated)
	footer := fmt.Sprintf("Refreshed %s ago • q to quit", timeSinceRefresh)

	return box + "\n" + footer
}

// renderCertLine formats the certificate expiry line with color coding.
func renderCertLine(certNotAfter time.Time) string {
	now := time.Now()
	if certNotAfter.IsZero() {
		return "Cert:    unknown"
	}

	if certNotAfter.Before(now) {
		expiredStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(ColorDanger))
		return "Cert:    " + expiredStyle.Render("expired")
	}

	daysLeft := int(certNotAfter.Sub(now).Hours() / 24)
	dateStr := certNotAfter.Format("2006-01-02")
	var certStyle lipgloss.Style

	if daysLeft < 7 {
		certStyle = lipgloss.NewStyle().Foreground(lipgloss.Color(ColorWarning))
		return "Cert:    " + certStyle.Render(fmt.Sprintf("valid until %s (%dd)", dateStr, daysLeft))
	}

	return fmt.Sprintf("Cert:    valid until %s (%dd)", dateStr, daysLeft)
}

// formatTimeSince formats a time.Time as a human-readable duration.
func formatTimeSince(t time.Time) string {
	if t.IsZero() {
		return "never"
	}
	elapsed := time.Since(t)
	if elapsed.Seconds() < 60 {
		return fmt.Sprintf("%.0fs", elapsed.Seconds())
	}
	if elapsed.Minutes() < 60 {
		return fmt.Sprintf("%.0fm", elapsed.Minutes())
	}
	return fmt.Sprintf("%.0fh", elapsed.Hours())
}

// RunDashboard runs the Bubble Tea program. Each tick calls fetch() to get a fresh snapshot.
// Refresh interval default = 2s. ctx cancellation (or 'q'/Ctrl+C) exits.
func RunDashboard(ctx context.Context, fetch func() DashboardSnapshot, interval time.Duration) error {
	// Get initial snapshot
	snapshot := fetch()

	m := model{
		fetch:      fetch,
		snapshot:   snapshot,
		lastUpdate: time.Now(),
	}

	p := tea.NewProgram(m)
	_, err := p.Run()
	return err
}
