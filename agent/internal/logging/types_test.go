package logging_test

import (
	"encoding/json"
	"testing"

	"github.com/hlhelper/hl-agent/internal/logging"
)

func TestLevelOrdering(t *testing.T) {
	if !(logging.LevelDebug < logging.LevelInfo &&
		logging.LevelInfo < logging.LevelWarn &&
		logging.LevelWarn < logging.LevelError &&
		logging.LevelError < logging.LevelCritical) {
		t.Fatal("level ordering wrong")
	}
}

func TestParseLevel(t *testing.T) {
	cases := map[string]logging.Level{
		"debug":    logging.LevelDebug,
		"info":     logging.LevelInfo,
		"warn":     logging.LevelWarn,
		"error":    logging.LevelError,
		"critical": logging.LevelCritical,
	}
	for k, v := range cases {
		got, err := logging.ParseLevel(k)
		if err != nil || got != v {
			t.Fatalf("%s: got %v err=%v want %v", k, got, err, v)
		}
	}
	if _, err := logging.ParseLevel("bogus"); err == nil {
		t.Fatal("expected error for unknown level")
	}
}

func TestLevelString(t *testing.T) {
	if logging.LevelString(logging.LevelWarn) != "warn" {
		t.Fatal("warn string wrong")
	}
}

func TestEventJSONRoundtrip(t *testing.T) {
	ev := logging.Event{
		ECSVersion: "8.11",
		Event: logging.EventFields{Kind: "event", Category: []string{"task"}, Action: "task.exec.completed", Outcome: "success", Sequence: 1, ID: "01HXY"},
		Agent: logging.AgentFields{ID: "a", Version: "0.4.1", Type: "hl-agent", SessionID: "s"},
		Host:  logging.HostFields{ID: "h", Name: "n"},
		Log:   logging.LogFields{Level: "info", Logger: "agent.task"},
		Labels: map[string]string{"k": "v"},
		Message: "ok",
		Details: map[string]any{"rc": 0},
	}
	b, err := json.Marshal(ev)
	if err != nil {
		t.Fatal(err)
	}
	var back logging.Event
	if err := json.Unmarshal(b, &back); err != nil {
		t.Fatal(err)
	}
	if back.Event.Action != "task.exec.completed" {
		t.Fatalf("action lost: %s", back.Event.Action)
	}
	if back.Agent.SessionID != "s" {
		t.Fatal("session lost")
	}
}
