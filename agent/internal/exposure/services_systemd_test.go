//go:build linux

package exposure

import (
	"testing"
)

const systemctlListUnitsOutput = `UNIT                                     LOAD   ACTIVE SUB     DESCRIPTION
nginx.service                            loaded active running A high performance web server
ssh.service                              loaded active running OpenSSH server
postgresql.service                       loaded inactive dead   PostgreSQL RDBMS
`

func TestParseSystemctlListUnits(t *testing.T) {
	out := parseSystemctlListUnits(systemctlListUnitsOutput)
	wantActive := map[string]bool{"nginx.service": true, "ssh.service": true}
	gotActive := map[string]bool{}
	for _, s := range out {
		if s.Active {
			gotActive[s.Name] = true
		}
	}
	for name := range wantActive {
		if !gotActive[name] {
			t.Errorf("expected %s active", name)
		}
	}
	if gotActive["postgresql.service"] {
		t.Error("postgresql should be inactive")
	}
}
