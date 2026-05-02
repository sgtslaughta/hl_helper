"""Generated protobuf bindings.

protoc emits absolute imports rooted at the proto path (`fleet.v1.*`).
Inject this package's directory onto sys.path so those imports resolve.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PB_ROOT = str(Path(__file__).parent)
if _PB_ROOT not in sys.path:
    sys.path.insert(0, _PB_ROOT)
