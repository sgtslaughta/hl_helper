package tui

import (
	"fmt"

	tea "github.com/charmbracelet/bubbletea"
)

type ConfirmChoice int

const (
	ConfirmCancel ConfirmChoice = iota
	ConfirmYes
	ConfirmNo
)

type Choice struct {
	Label       string
	Description string
}

// Confirm shows yes/no prompt. Returns ConfirmYes / ConfirmNo / ConfirmCancel (Esc/Ctrl-C).
func Confirm(prompt string) (ConfirmChoice, error) {
	p := tea.NewProgram(newConfirmModel(prompt))
	model, err := p.Run()
	if err != nil {
		return ConfirmCancel, err
	}

	m := model.(confirmModel)
	return m.choice, nil
}

// Select shows arrow-key list of choices; returns selected index or -1 on cancel.
func Select(prompt string, choices []Choice) (int, error) {
	p := tea.NewProgram(newSelectModel(prompt, choices))
	model, err := p.Run()
	if err != nil {
		return -1, err
	}

	m := model.(selectModel)
	return m.selected, nil
}

// confirmModel is a bubbletea model for yes/no confirmation.
type confirmModel struct {
	prompt string
	choice ConfirmChoice
}

func newConfirmModel(prompt string) confirmModel {
	return confirmModel{
		prompt: prompt,
		choice: ConfirmCancel,
	}
}

func (m confirmModel) Init() tea.Cmd {
	return nil
}

func (m confirmModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.Type {
		case tea.KeyCtrlC, tea.KeyEsc:
			return m, tea.Quit
		}

		switch msg.String() {
		case "y", "Y":
			m.choice = ConfirmYes
			return m, tea.Quit
		case "n", "N":
			m.choice = ConfirmNo
			return m, tea.Quit
		}
	}
	return m, nil
}

func (m confirmModel) View() string {
	return fmt.Sprintf("%s (y/n): ", m.prompt)
}

// selectModel is a bubbletea model for arrow-key selection.
type selectModel struct {
	prompt   string
	choices  []Choice
	cursor   int
	selected int
	done     bool
}

func newSelectModel(prompt string, choices []Choice) selectModel {
	return selectModel{
		prompt:   prompt,
		choices:  choices,
		cursor:   0,
		selected: -1,
		done:     false,
	}
}

func (m selectModel) Init() tea.Cmd {
	return nil
}

func (m selectModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.Type {
		case tea.KeyCtrlC, tea.KeyEsc:
			m.selected = -1
			m.done = true
			return m, tea.Quit
		case tea.KeyUp:
			if m.cursor > 0 {
				m.cursor--
			}
		case tea.KeyDown:
			if m.cursor < len(m.choices)-1 {
				m.cursor++
			}
		case tea.KeyEnter:
			m.selected = m.cursor
			m.done = true
			return m, tea.Quit
		}
	}
	return m, nil
}

func (m selectModel) View() string {
	var view string
	if m.prompt != "" {
		view = m.prompt + "\n\n"
	}

	for i, choice := range m.choices {
		cursor := "  "
		if i == m.cursor {
			cursor = StyleAccent.Render("→ ")
		}

		line := fmt.Sprintf("%s%s", cursor, choice.Label)
		if choice.Description != "" {
			line = fmt.Sprintf("%s - %s", line, choice.Description)
		}
		view += line + "\n"
	}

	if m.done {
		return ""
	}
	return view
}
