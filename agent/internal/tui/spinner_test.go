package tui

import (
	"bytes"
	"errors"
	"strings"
	"testing"
)

func TestRunSpinnerSuccess(t *testing.T) {
	buf := &bytes.Buffer{}
	called := false

	fn := func() error {
		called = true
		return nil
	}

	err := RunSpinner(buf, "doing work", fn)

	if err != nil {
		t.Errorf("RunSpinner should not return error on success, got %v", err)
	}

	if !called {
		t.Errorf("RunSpinner should call the function")
	}

	output := buf.String()
	if !strings.Contains(output, "doing work") {
		t.Errorf("RunSpinner output should contain message, got: %q", output)
	}

	if !strings.Contains(output, "done") || !strings.Contains(output, GlyphCheck) {
		t.Errorf("RunSpinner output should contain done indicator with check, got: %q", output)
	}
}

func TestRunSpinnerError(t *testing.T) {
	buf := &bytes.Buffer{}
	testErr := errors.New("something went wrong")

	fn := func() error {
		return testErr
	}

	err := RunSpinner(buf, "doing work", fn)

	if err != testErr {
		t.Errorf("RunSpinner should return the error from fn, got %v, want %v", err, testErr)
	}

	output := buf.String()
	if !strings.Contains(output, "doing work") {
		t.Errorf("RunSpinner output should contain message, got: %q", output)
	}

	if !strings.Contains(output, testErr.Error()) {
		t.Errorf("RunSpinner output should contain error message, got: %q", output)
	}
}

func TestRunSpinnerReturnsError(t *testing.T) {
	buf := &bytes.Buffer{}
	testErr := errors.New("test error")

	fn := func() error {
		return testErr
	}

	err := RunSpinner(buf, "test", fn)
	if err == nil {
		t.Errorf("RunSpinner should return error when fn returns error")
	}
	if err != testErr {
		t.Errorf("RunSpinner should return the exact error, got %v want %v", err, testErr)
	}
}
