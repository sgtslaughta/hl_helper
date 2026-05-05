# Contributing

Guide for developers contributing to HL Helper.

!!! note "Under construction"
    Detailed contributing guide is being written. Check back soon.

## Development Setup

```bash
git clone https://github.com/hlhelper/hl_helper.git
cd hl_helper
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e '.[dev,docs]'
```

## Running Tests

```bash
pytest server/tests/ -v
```

## Building Documentation

```bash
zensical serve
```

Visit `http://127.0.0.1:8000` to preview the documentation locally.

## Code Style

- Python: enforced by `ruff` (line length 100, target Python 3.12)
- Go: standard `gofmt`
- Type checking: `mypy --strict` for Python
