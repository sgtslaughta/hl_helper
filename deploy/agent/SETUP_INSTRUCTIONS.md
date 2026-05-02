# Setup Instructions for hl-agent Build Scripts

The build scripts (`build.sh` and `build_native.sh`) require executable permissions to function properly.

## Automatic Setup

Run the setup script to automatically set permissions:

```bash
python3 deploy/agent/setup.py
```

## Manual Setup

If automatic setup is not available, manually set permissions using:

```bash
chmod +x deploy/agent/build.sh
chmod +x deploy/agent/build_native.sh
```

Or using git to mark them as executable in the repository:

```bash
git update-index --chmod=+x deploy/agent/build.sh deploy/agent/build_native.sh
```

## Verification

After setup, verify the permissions:

```bash
ls -la deploy/agent/build.sh deploy/agent/build_native.sh
```

They should show `-rwxr-xr-x` (or similar with execute bits set for owner, group, and others).
