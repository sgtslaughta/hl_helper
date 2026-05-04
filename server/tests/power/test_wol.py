"""Tests for WOL sender module."""

from __future__ import annotations

import asyncio
import socket

import pytest

from server.app.power.wol import (
    InvalidMacError,
    WolSender,
    build_magic_packet,
)


class TestBuildMagicPacket:
    """Tests for build_magic_packet function."""

    def test_magic_packet_length_no_password(self) -> None:
        """Magic packet without password should be 102 bytes."""
        packet = build_magic_packet("aa:bb:cc:dd:ee:ff")
        assert len(packet) == 102

    def test_magic_packet_length_with_password(self) -> None:
        """Magic packet with password should be 108 bytes."""
        packet = build_magic_packet("aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66")
        assert len(packet) == 108

    def test_magic_packet_starts_with_six_0xff(self) -> None:
        """Magic packet should start with 6 bytes of 0xFF."""
        packet = build_magic_packet("aa:bb:cc:dd:ee:ff")
        assert packet[:6] == b"\xff\xff\xff\xff\xff\xff"

    def test_magic_packet_mac_repeated_16_times(self) -> None:
        """MAC address should be repeated 16 times after 0xFF preamble."""
        mac = "aa:bb:cc:dd:ee:ff"
        packet = build_magic_packet(mac)

        # Extract the MAC part (after first 6 bytes of 0xFF)
        mac_bytes = bytes.fromhex("aabbccddeeff")
        for i in range(16):
            offset = 6 + (i * 6)
            assert packet[offset : offset + 6] == mac_bytes

    def test_mac_format_colon_separated(self) -> None:
        """Accept MAC format with colons (aa:bb:cc:dd:ee:ff)."""
        packet1 = build_magic_packet("aa:bb:cc:dd:ee:ff")
        packet2 = build_magic_packet("AA:BB:CC:DD:EE:FF")
        assert len(packet1) == 102
        assert packet1 == packet2

    def test_mac_format_dash_separated(self) -> None:
        """Accept MAC format with dashes (aa-bb-cc-dd-ee-ff)."""
        packet1 = build_magic_packet("aa-bb-cc-dd-ee-ff")
        packet2 = build_magic_packet("aa:bb:cc:dd:ee:ff")
        assert packet1 == packet2

    def test_mac_format_no_separator(self) -> None:
        """Accept MAC format without separators (aabbccddeeff)."""
        packet1 = build_magic_packet("aabbccddeeff")
        packet2 = build_magic_packet("aa:bb:cc:dd:ee:ff")
        assert packet1 == packet2

    def test_mac_case_insensitive(self) -> None:
        """MAC addresses should be case-insensitive."""
        packet1 = build_magic_packet("aa:bb:cc:dd:ee:ff")
        packet2 = build_magic_packet("AA:BB:CC:DD:EE:FF")
        packet3 = build_magic_packet("AaBbCcDdEeFf")
        assert packet1 == packet2 == packet3

    def test_invalid_mac_empty(self) -> None:
        """Empty MAC should raise InvalidMacError."""
        with pytest.raises(InvalidMacError):
            build_magic_packet("")

    def test_invalid_mac_wrong_length(self) -> None:
        """MAC with wrong number of octets should raise InvalidMacError."""
        with pytest.raises(InvalidMacError):
            build_magic_packet("aa:bb:cc:dd:ee")

        with pytest.raises(InvalidMacError):
            build_magic_packet("aa:bb:cc:dd:ee:ff:00")

    def test_invalid_mac_non_hex_chars(self) -> None:
        """MAC with non-hex characters should raise InvalidMacError."""
        with pytest.raises(InvalidMacError):
            build_magic_packet("gg:bb:cc:dd:ee:ff")

        with pytest.raises(InvalidMacError):
            build_magic_packet("aa:bb:cc:dd:ee:zz")

    def test_password_format_colon_separated(self) -> None:
        """SecureOn password format with colons (xx:xx:xx:xx:xx:xx)."""
        packet = build_magic_packet(
            "aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"
        )
        # Password should be appended at the end
        assert packet[-6:] == bytes.fromhex("112233445566")

    def test_password_format_no_separator(self) -> None:
        """SecureOn password format without separators."""
        packet1 = build_magic_packet("aa:bb:cc:dd:ee:ff", "112233445566")
        packet2 = build_magic_packet("aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66")
        assert packet1 == packet2

    def test_password_case_insensitive(self) -> None:
        """SecureOn password should be case-insensitive."""
        packet1 = build_magic_packet("aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff")
        packet2 = build_magic_packet("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF")
        assert packet1 == packet2


class TestWolSender:
    """Tests for WolSender class."""

    def test_default_broadcasts(self) -> None:
        """WolSender should use default broadcast address."""
        sender = WolSender()
        assert sender.broadcasts == ["255.255.255.255"]

    def test_custom_broadcasts(self) -> None:
        """WolSender should accept custom broadcast addresses."""
        broadcasts = ["192.168.1.255", "192.168.2.255"]
        sender = WolSender(broadcasts=broadcasts)
        assert sender.broadcasts == broadcasts

    def test_custom_port(self) -> None:
        """WolSender should accept custom port."""
        sender = WolSender(port=7)
        assert sender.port == 7

    def test_default_port(self) -> None:
        """WolSender should default to port 9."""
        sender = WolSender()
        assert sender.port == 9

    @pytest.mark.asyncio
    async def test_send_returns_count(self) -> None:
        """send() should return count of successful broadcasts."""
        # Create a simple UDP listener on localhost
        listener_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener_sock.bind(("127.0.0.1", 0))
        _, port = listener_sock.getsockname()

        received_packets: list[bytes] = []

        async def listen() -> None:
            """Listen for packets in background."""
            loop = asyncio.get_event_loop()
            while len(received_packets) < 1:
                try:
                    data = await asyncio.wait_for(
                        loop.sock_recv(listener_sock, 1024), timeout=2.0
                    )
                    received_packets.append(data)
                except asyncio.TimeoutError:
                    break

        # Start listener
        listener_task = asyncio.create_task(listen())

        # Send WOL packet
        sender = WolSender(broadcasts=["127.0.0.1"], port=port)
        count = await sender.send("aa:bb:cc:dd:ee:ff")

        # Wait for listener
        try:
            await asyncio.wait_for(listener_task, timeout=3.0)
        except asyncio.TimeoutError:
            pass

        listener_sock.close()

        # Verify
        assert count == 1
        assert len(received_packets) == 1

    @pytest.mark.asyncio
    async def test_send_packet_format(self) -> None:
        """send() should send correct magic packet format."""
        listener_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener_sock.bind(("127.0.0.1", 0))
        _, port = listener_sock.getsockname()

        received_packets: list[bytes] = []

        async def listen() -> None:
            """Listen for packets in background."""
            loop = asyncio.get_event_loop()
            while len(received_packets) < 1:
                try:
                    data = await asyncio.wait_for(
                        loop.sock_recv(listener_sock, 1024), timeout=2.0
                    )
                    received_packets.append(data)
                except asyncio.TimeoutError:
                    break

        listener_task = asyncio.create_task(listen())

        mac = "aa:bb:cc:dd:ee:ff"
        sender = WolSender(broadcasts=["127.0.0.1"], port=port)
        await sender.send(mac)

        try:
            await asyncio.wait_for(listener_task, timeout=3.0)
        except asyncio.TimeoutError:
            pass

        listener_sock.close()

        # Verify packet format
        expected_packet = build_magic_packet(mac)
        assert len(received_packets) == 1
        assert received_packets[0] == expected_packet

    @pytest.mark.asyncio
    async def test_send_multiple_broadcasts(self) -> None:
        """send() should return count matching broadcast count."""
        # Test that send() attempts to send to all configured broadcasts
        # We verify count matches broadcasts list length by setting to local addresses
        sender = WolSender(
            broadcasts=["127.0.0.1", "127.0.0.1", "127.0.0.1"],
            port=9999
        )
        # With unreachable port, it will fail silently (caught exception)
        # but still attempt all broadcasts and return count
        count = await sender.send("aa:bb:cc:dd:ee:ff")
        # Count is attempts despite failures (exception caught in loop)
        assert count == 3
