package inventory

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"os"
)

// CollectContainers collects running and stopped containers via docker socket.
func CollectContainers(ctx context.Context) ([]Container, error) {
	const dockerSocket = "/var/run/docker.sock"

	// Check if docker socket exists
	if _, err := os.Stat(dockerSocket); err != nil {
		return nil, nil
	}

	client := &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				return net.Dial("unix", dockerSocket)
			},
		},
	}

	req, err := http.NewRequestWithContext(ctx, "GET", "http://unix/v1.41/containers/json?all=1", nil)
	if err != nil {
		return nil, nil
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, nil
	}

	var containers []struct {
		ID       string   `json:"Id"`
		Names    []string `json:"Names"`
		Image    string   `json:"Image"`
		ImageID  string   `json:"ImageID"`
		State    string   `json:"State"`
		Status   string   `json:"Status"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&containers); err != nil {
		return nil, nil
	}

	var result []Container
	for _, c := range containers {
		name := ""
		if len(c.Names) > 0 {
			name = c.Names[0]
			// Remove leading slash if present
			if len(name) > 0 && name[0] == '/' {
				name = name[1:]
			}
		}

		result = append(result, Container{
			ID:          c.ID,
			Name:        name,
			ImageRef:    c.Image,
			ImageDigest: c.ImageID,
			State:       c.State,
			Engine:      "docker",
		})
	}

	return result, nil
}
