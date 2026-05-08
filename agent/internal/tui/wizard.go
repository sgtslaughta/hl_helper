package tui

import (
	"fmt"
	"io"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/bubbles/textinput"
)

type WizardConfig struct {
	InitKind string
	Server   string
	Token    string
	Hostname string
}

type WizardResult struct {
	Server    string
	Token     string
	Hostname  string
	Confirmed bool
}

// Wizard is a bubble tea model for interactive installation.
type wizard struct {
	step     int
	cfg      WizardConfig
	result   WizardResult
	input    textinput.Model
	err      error
	quitting bool
}

const (
	stepDetect   = 0
	stepServer   = 1
	stepToken    = 2
	stepHostname = 3
	stepConfirm  = 4
	stepDone     = 5
)

// RunWizard launches the interactive TUI wizard and returns the confirmed values.
func RunWizard(cfg WizardConfig, w io.Writer) (WizardResult, error) {
	p := tea.NewProgram(newWizard(cfg))
	model, err := p.Run()
	if err != nil {
		return WizardResult{}, err
	}

	m := model.(wizard)
	if m.err != nil {
		return WizardResult{}, m.err
	}

	if !m.result.Confirmed {
		return WizardResult{}, fmt.Errorf("installation cancelled")
	}

	return m.result, nil
}

func maskToken(s string) string {
	if len(s) <= 4 {
		return "••••"
	}
	return "••••" + s[len(s)-4:]
}

func newWizard(cfg WizardConfig) wizard {
	ti := textinput.New()
	ti.CharLimit = 256

	return wizard{
		step: stepDetect,
		cfg:  cfg,
		result: WizardResult{
			Server:   cfg.Server,
			Token:    cfg.Token,
			Hostname: cfg.Hostname,
		},
		input: ti,
	}
}

func (m wizard) Init() tea.Cmd {
	return nil
}

func (m wizard) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.Type {
		case tea.KeyCtrlC:
			m.quitting = true
			return m, tea.Quit

		case tea.KeyEnter:
			switch m.step {
			case stepDetect:
				m.step = stepServer
				m.input.SetValue(m.result.Server)
				m.input.Focus()
				return m, nil

			case stepServer:
				m.result.Server = m.input.Value()
				if m.result.Server == "" {
					m.err = fmt.Errorf("server URL is required")
					m.step = stepDone
					return m, tea.Quit
				}
				m.step = stepToken
				m.input.SetValue("")
				m.input.EchoMode = textinput.EchoNone
				m.input.EchoCharacter = '•'
				return m, nil

			case stepToken:
				m.result.Token = m.input.Value()
				if m.result.Token == "" {
					m.err = fmt.Errorf("enrollment token is required")
					m.step = stepDone
					return m, tea.Quit
				}
				m.step = stepHostname
				m.input.SetValue(m.result.Hostname)
				m.input.EchoMode = textinput.EchoNormal
				return m, nil

			case stepHostname:
				m.result.Hostname = m.input.Value()
				if m.result.Hostname == "" {
					if h, err := os.Hostname(); err == nil {
						m.result.Hostname = h
					}
				}
				m.step = stepConfirm
				m.input.Blur()
				return m, nil

			case stepConfirm:
				// Should not reach here; confirmation uses y/n
				return m, nil
			}

		case tea.KeyRunes:
			if m.step == stepConfirm {
				switch string(msg.Runes) {
				case "y", "Y":
					m.result.Confirmed = true
					m.step = stepDone
					return m, tea.Quit
				case "n", "N":
					m.result.Confirmed = false
					m.step = stepDone
					return m, tea.Quit
				}
			}

		default:
			if m.step >= stepDetect && m.step < stepConfirm {
				var cmd tea.Cmd
				m.input, cmd = m.input.Update(msg)
				return m, cmd
			}
		}

	case tea.WindowSizeMsg:
		// Ignore window size
	}

	return m, nil
}

func (m wizard) View() string {
	if m.quitting || m.step == stepDone {
		return ""
	}

	var view string

	switch m.step {
	case stepDetect:
		view = fmt.Sprintf("Detected init system: %s\nPress Enter to continue...", m.cfg.InitKind)

	case stepServer:
		view = fmt.Sprintf(
			"Server enrollment URL (UI/API endpoint, e.g. https://hl.example.com)\n"+
				"  The gRPC streaming endpoint will be returned by the server.\n\n"+
				"URL [%s]:\n%s",
			m.result.Server, m.input.View())

	case stepToken:
		view = fmt.Sprintf("Enrollment token (one-time, from server admin):\n%s", m.input.View())

	case stepHostname:
		view = fmt.Sprintf("Hostname [%s]:\n%s", m.result.Hostname, m.input.View())

	case stepConfirm:
		view = fmt.Sprintf(
			"Confirm installation:\n"+
				"  Enrollment URL: %s\n"+
				"  Token:          %s\n"+
				"  Hostname:       %s\n\n"+
				"The server will return the gRPC endpoint for ongoing communication.\n"+
				"Proceed? (y/n)",
			m.result.Server, maskToken(m.result.Token), m.result.Hostname)
	}

	return view
}
