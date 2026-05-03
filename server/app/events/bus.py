"""In-process asyncio-based event bus with per-channel pub/sub and backpressure."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Mapping


class _Sentinel:
    """Sentinel value to signal subscription closure."""

    pass


@dataclass(frozen=True)
class Event:
    """Immutable event published on the bus.

    Attributes:
        sequence: Global monotonic event sequence number.
        channel: Arbitrary string channel key (e.g., 'commands', 'hosts.status').
        payload: Event data (immutable mapping).
        timestamp: UTC datetime when event was published.
    """

    sequence: int
    channel: str
    payload: Mapping[str, Any]
    timestamp: datetime


class Subscription:
    """Active subscription to a bus channel.

    Provides async iteration over events and a close() method to unsubscribe.
    """

    def __init__(
        self,
        bus: Bus,
        channel: str,
        queue: asyncio.Queue[Event | _Sentinel],
    ) -> None:
        """Initialize subscription.

        Args:
            bus: Parent Bus instance.
            channel: Channel name.
            queue: Bounded queue for this subscription.
        """
        self._bus = bus
        self._channel = channel
        self._queue = queue
        self._closed = False
        self._dropped_since_advisory = 0

    async def close(self) -> None:
        """Close this subscription and unsubscribe from the bus."""
        self._closed = True
        self._bus._unsubscribe(self._channel, self)
        # Put sentinel to wake up any waiting __anext__
        try:
            self._queue.put_nowait(_Sentinel())
        except asyncio.QueueFull:
            pass  # Queue is full; sentinel couldn't be added, but close flag is set

    def __aiter__(self) -> AsyncIterator[Event]:
        """Async iteration support."""
        return self

    async def __anext__(self) -> Event:
        """Get next event or raise StopAsyncIteration if closed.

        Yields a pending backpressure advisory before next queued event when drops
        have occurred. Advisory is generated out-of-band so it is not subject to
        the bounded queue capacity.
        """
        if self._closed:
            raise StopAsyncIteration
        if self._dropped_since_advisory > 0:
            # Advisory uses sentinel sequence 0 — it is not a published event
            # and must not occupy a real sequence slot in the monotonic stream.
            advisory = Event(
                sequence=0,
                channel=f"_backpressure.{self._channel}",
                payload={"dropped_count": self._dropped_since_advisory},
                timestamp=datetime.now(timezone.utc),
            )
            self._dropped_since_advisory = 0
            return advisory
        try:
            item = await self._queue.get()
            if isinstance(item, _Sentinel):
                raise StopAsyncIteration
            return item
        except asyncio.CancelledError:
            raise StopAsyncIteration


class Bus:
    """In-process asyncio event bus with per-channel pub/sub and backpressure handling.

    - Publishes events with monotonically increasing sequence numbers.
    - Supports arbitrary string channels.
    - Per-subscription bounded queues with backpressure (drops oldest, sends advisory).
    - Resume capability: new subscribers can request events since a given sequence.
    - Ring buffer of recent events per channel for resume support (LRU eviction).
    """

    def __init__(self, ring_buffer_size: int = 256, max_channels: int = 1024) -> None:
        """Initialize the bus.

        Args:
            ring_buffer_size: Number of recent events to keep per channel for resume.
            max_channels: Maximum number of distinct channels to keep ring buffers for.
                When exceeded, least-recently-used channel buffer is evicted.
        """
        self._sequence = 0
        self._sequence_lock = asyncio.Lock()
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._max_channels = max_channels
        # Ring buffer per channel using OrderedDict for LRU eviction.
        # move_to_end() on access; popitem(last=False) to evict oldest when full.
        self._ring_buffers: OrderedDict[str, deque[Event]] = OrderedDict()
        self._ring_buffer_size = ring_buffer_size

    async def publish(self, channel: str, payload: Mapping[str, Any]) -> Event:
        """Publish an event to a channel.

        Args:
            channel: Destination channel name.
            payload: Event payload (arbitrary mapping).

        Returns:
            The published Event with assigned sequence, channel, timestamp.
        """
        async with self._sequence_lock:
            self._sequence += 1
            seq = self._sequence

        now = datetime.now(timezone.utc)
        event = Event(
            sequence=seq,
            channel=channel,
            payload=payload,
            timestamp=now,
        )

        # Store in ring buffer for resume support
        if channel not in self._ring_buffers:
            # Evict LRU channel if at capacity
            if len(self._ring_buffers) >= self._max_channels:
                self._ring_buffers.popitem(last=False)
            # Create new ring buffer
            self._ring_buffers[channel] = deque(maxlen=self._ring_buffer_size)
        else:
            # Move channel to end (most recently used)
            self._ring_buffers.move_to_end(channel)

        self._ring_buffers[channel].append(event)

        # Send to all subscribers on this channel
        if channel in self._subscriptions:
            for sub in list(self._subscriptions[channel]):
                self._send_to_subscriber(sub, event)

        return event

    def _send_to_subscriber(self, sub: Subscription, event: Event) -> None:
        """Send event to subscriber, handling backpressure.

        When queue is full, drop oldest event to make room and increment the
        subscription's drop counter. Subscription emits an advisory event
        out-of-band on next __anext__ call.
        """
        try:
            sub._queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                sub._queue.get_nowait()
                sub._dropped_since_advisory += 1
            except asyncio.QueueEmpty:
                pass
            try:
                sub._queue.put_nowait(event)
            except asyncio.QueueFull:
                sub._dropped_since_advisory += 1

    def subscribe(
        self,
        channel: str,
        *,
        since_sequence: int | None = None,
        max_queue: int = 1024,
    ) -> Subscription:
        """Subscribe to a channel.

        Args:
            channel: Channel name.
            since_sequence: If provided, replay buffered events with sequence > since_sequence.
            max_queue: Maximum queue size for this subscription (bounded backpressure).

        Returns:
            Subscription object with async iteration and close() method.
        """
        queue: asyncio.Queue[Event | _Sentinel] = asyncio.Queue(maxsize=max_queue)
        sub = Subscription(self, channel, queue)

        # Register subscription
        if channel not in self._subscriptions:
            self._subscriptions[channel] = []
        self._subscriptions[channel].append(sub)

        # Mark channel as accessed in ring buffers (LRU)
        if channel in self._ring_buffers:
            self._ring_buffers.move_to_end(channel)

        # Replay buffered events if since_sequence provided
        if since_sequence is not None and channel in self._ring_buffers:
            for event in self._ring_buffers[channel]:
                if event.sequence > since_sequence:
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        break

        return sub

    def _unsubscribe(self, channel: str, sub: Subscription) -> None:
        """Internal: remove subscription from channel.

        Args:
            channel: Channel name.
            sub: Subscription to remove.
        """
        if channel in self._subscriptions:
            try:
                self._subscriptions[channel].remove(sub)
            except ValueError:
                pass
            if not self._subscriptions[channel]:
                del self._subscriptions[channel]
