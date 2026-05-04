"""C10 power controls — WOL sender + (future) reboot/shutdown via dispatcher."""

from __future__ import annotations

from server.app.power.wol import (
    InvalidMacError,
    WolError,
    WolSender,
    build_magic_packet,
)

__all__ = ["WolSender", "WolError", "InvalidMacError", "build_magic_packet"]
