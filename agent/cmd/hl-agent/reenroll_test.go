package main

import (
	"testing"
)

func TestReenrollFlagsParse(t *testing.T) {
	cmd := newReenrollCmd()
	if err := cmd.ParseFlags([]string{
		"--url", "https://srv.example:7444",
		"--token", "hlb_xyz",
	}); err != nil {
		t.Fatalf("ParseFlags: %v", err)
	}
	url, _ := cmd.Flags().GetString("url")
	token, _ := cmd.Flags().GetString("token")
	if url != "https://srv.example:7444" || token != "hlb_xyz" {
		t.Errorf("flags: url=%q token=%q", url, token)
	}
}
