package enrollment

import (
	"crypto/sha256"
	"strconv"
)

// CanonicalReenrollPayload mirrors the server-side payload exactly:
// sha256("reenroll-v1|" + host_id + "|" + nonce + "|" + ts_unix)
func CanonicalReenrollPayload(hostID string, nonce []byte, tsUnix int64) []byte {
	body := []byte("reenroll-v1|")
	body = append(body, []byte(hostID)...)
	body = append(body, '|')
	body = append(body, nonce...)
	body = append(body, '|')
	body = append(body, []byte(strconv.FormatInt(tsUnix, 10))...)
	digest := sha256.Sum256(body)
	return digest[:]
}
