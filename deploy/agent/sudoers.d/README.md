# hl_helper agent sudoers fragments

Per-distribution sudoers configuration fragments for the hl-agent user.

## Installation

Choose the appropriate fragment for your distribution and copy it to `/etc/sudoers.d/hl-agent`:

### Debian / Ubuntu

```bash
sudo install -m 0440 hl-agent-debian /etc/sudoers.d/hl-agent
```

### RHEL / Fedora / Rocky

```bash
sudo install -m 0440 hl-agent-rhel /etc/sudoers.d/hl-agent
```

### Arch Linux

```bash
sudo install -m 0440 hl-agent-arch /etc/sudoers.d/hl-agent
```

### Alpine Linux

```bash
sudo install -m 0440 hl-agent-alpine /etc/sudoers.d/hl-agent
```

## Validation

After installation, verify the sudoers file is syntactically correct:

```bash
sudo visudo -c -f /etc/sudoers.d/hl-agent
```
