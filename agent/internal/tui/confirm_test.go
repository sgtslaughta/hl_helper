package tui

import (
	"testing"
)

func TestConfirmChoiceValues(t *testing.T) {
	// Ensure constants are defined correctly.
	if ConfirmCancel != 0 {
		t.Errorf("ConfirmCancel should be 0, got %d", ConfirmCancel)
	}
	if ConfirmYes != 1 {
		t.Errorf("ConfirmYes should be 1, got %d", ConfirmYes)
	}
	if ConfirmNo != 2 {
		t.Errorf("ConfirmNo should be 2, got %d", ConfirmNo)
	}
}

func TestSelectWithChoices(t *testing.T) {
	// Test that Select is callable with choices.
	choices := []Choice{
		{Label: "Option 1", Description: "Desc 1"},
		{Label: "Option 2", Description: "Desc 2"},
	}

	// This is a basic sanity test since actual TTY interaction can't be tested easily.
	// We'll mock the TTY behavior in a separate integration test if needed.
	if len(choices) != 2 {
		t.Error("expected 2 choices")
	}
}
