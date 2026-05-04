"""Wake-on-LAN sender implementation."""

from __future__ import annotations

import asyncio
import socket

import structlog

_log = structlog.get_logger(__name__)


class WolError(Exception):
    """Base exception for WOL errors."""

    pass


class InvalidMacError(WolError):
    """Raised when MAC address format is invalid."""

    pass


def build_magic_packet(mac: str, password: str | None = None) -> bytes:
    """Build a Wake-on-LAN magic packet.

    Args:
        mac: MAC address in format aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff,
             or aabbccddeeff (case-insensitive).
        password: Optional SecureOn password in format xx:xx:xx:xx:xx:xx
                  or xxxxxxxxxxxxxxxx (case-insensitive).

    Returns:
        Magic packet as bytes (102 bytes without password, 108 with).

    Raises:
        InvalidMacError: If MAC address is malformed.
    """
    # Normalize and parse MAC address
    mac_clean = mac.replace(":", "").replace("-", "").lower()

    if not mac_clean or len(mac_clean) != 12:
        raise InvalidMacError(
            f"Invalid MAC address: {mac}. Expected 6 octets."
        )

    try:
        mac_bytes = bytes.fromhex(mac_clean)
    except ValueError as e:
        raise InvalidMacError(f"Invalid MAC address: {mac}. {e}") from e

    # Build packet: 6x0xFF + MAC repeated 16 times
    packet = b"\xff" * 6 + mac_bytes * 16

    # Add password if provided
    if password is not None:
        pwd_clean = password.replace(":", "").lower()
        if len(pwd_clean) != 12:
            raise InvalidMacError(
                f"Invalid password: {password}. Expected 6 octets."
            )
        try:
            pwd_bytes = bytes.fromhex(pwd_clean)
        except ValueError as e:
            raise InvalidMacError(f"Invalid password: {password}. {e}") from e
        packet += pwd_bytes

    return packet


class WolSender:
    """Wake-on-LAN packet sender."""

    def __init__(
        self, broadcasts: list[str] | None = None, port: int = 9
    ) -> None:
        """Initialize WOL sender.

        Args:
            broadcasts: List of broadcast addresses. Defaults to ["255.255.255.255"].
            port: UDP port for WOL packets. Defaults to 9.
        """
        self.broadcasts = broadcasts or ["255.255.255.255"]
        self.port = port

    async def send(
        self, mac: str, password: str | None = None
    ) -> int:
        """Send WOL packet to all broadcast addresses.

        Args:
            mac: MAC address of target device.
            password: Optional SecureOn password.

        Returns:
            Number of successful broadcast sends.
        """
        packet = build_magic_packet(mac, password)
        count = 0

        for broadcast_addr in self.broadcasts:
            try:
                await self._send_to_broadcast(broadcast_addr, packet)
                count += 1
            except OSError as exc:
                _log.warning(
                    "wol.broadcast_failed",
                    broadcast=broadcast_addr,
                    port=self.port,
                    error=str(exc),
                )

        return count

    async def _send_to_broadcast(
        self, broadcast_addr: str, packet: bytes
    ) -> None:
        """Send packet to a single broadcast address.

        Args:
            broadcast_addr: Broadcast address to send to.
            packet: Packet data to send.
        """
        loop = asyncio.get_event_loop()

        def send_packet() -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                sock.sendto(packet, (broadcast_addr, self.port))
            finally:
                sock.close()

        await loop.run_in_executor(None, send_packet)
