package inventory

type Pkg struct {
	Ecosystem string
	Name      string
	Version   string
	Source    string
	Arch      string
}

type Container struct {
	ID          string
	Name        string
	ImageRef    string
	ImageDigest string
	State       string
	Engine      string
}

type Facts struct {
	SSHD    map[string]string
	Sysctl  map[string]string
	Mounts  []string
	FsPerms map[string]string
}
