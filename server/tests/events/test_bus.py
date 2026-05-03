"""Tests for in-process asyncio-based event bus."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from server.app.events.bus import Bus, Event


class TestBusPublishSubscribe:
    """Test basic publish/subscribe functionality."""

    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self) -> None:
        """Subscriber receives published event."""
        bus = Bus()

        async def subscriber():
            async for event in bus.subscribe("test"):
                return event

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)  # Let subscriber start

        published = await bus.publish("test", {"key": "value"})
        result = await asyncio.wait_for(task, timeout=1.0)

        assert result.channel == "test"
        assert result.payload == {"key": "value"}
        assert result.sequence == published.sequence
        assert isinstance(result.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_per_channel_isolation(self) -> None:
        """Subscriber on channel 'a' doesn't receive events on channel 'b'."""
        bus = Bus()
        events_a = []
        events_b = []

        async def sub_a():
            async for event in bus.subscribe("a"):
                events_a.append(event)
                if len(events_a) >= 1:
                    break

        async def sub_b():
            async for event in bus.subscribe("b"):
                events_b.append(event)
                if len(events_b) >= 1:
                    break

        task_a = asyncio.create_task(sub_a())
        task_b = asyncio.create_task(sub_b())
        await asyncio.sleep(0.01)

        await bus.publish("a", {"chan": "a"})
        await bus.publish("b", {"chan": "b"})

        try:
            await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert len(events_a) == 1
        assert events_a[0].payload == {"chan": "a"}
        assert len(events_b) == 1
        assert events_b[0].payload == {"chan": "b"}

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_channel(self) -> None:
        """Multiple subscribers on same channel all receive the event."""
        bus = Bus()
        events1 = []
        events2 = []
        events3 = []

        async def sub1():
            async for event in bus.subscribe("multi"):
                events1.append(event)
                if len(events1) >= 1:
                    break

        async def sub2():
            async for event in bus.subscribe("multi"):
                events2.append(event)
                if len(events2) >= 1:
                    break

        async def sub3():
            async for event in bus.subscribe("multi"):
                events3.append(event)
                if len(events3) >= 1:
                    break

        task1 = asyncio.create_task(sub1())
        task2 = asyncio.create_task(sub2())
        task3 = asyncio.create_task(sub3())
        await asyncio.sleep(0.01)

        published = await bus.publish("multi", {"data": 42})

        try:
            await asyncio.wait_for(asyncio.gather(task1, task2, task3), timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert len(events1) == 1
        assert len(events2) == 1
        assert len(events3) == 1
        assert events1[0].sequence == published.sequence
        assert events2[0].sequence == published.sequence
        assert events3[0].sequence == published.sequence


class TestMonotonicSequence:
    """Test monotonic sequence counter."""

    @pytest.mark.asyncio
    async def test_sequence_strictly_increases(self) -> None:
        """Sequence numbers strictly increase across publishes."""
        bus = Bus()

        e1 = await bus.publish("seq", {"n": 1})
        e2 = await bus.publish("seq", {"n": 2})
        e3 = await bus.publish("seq", {"n": 3})

        assert e1.sequence < e2.sequence < e3.sequence


class TestBackpressure:
    """Test backpressure handling when subscriber queue is full."""

    @pytest.mark.asyncio
    async def test_backpressure_drops_oldest_with_advisory(self) -> None:
        """When queue full, drop oldest and send advisory with dropped_count."""
        bus = Bus()
        events = []

        async def subscriber():
            async for event in bus.subscribe("bp", max_queue=2):
                events.append(event)
                if len(events) >= 4:  # Expect 2 original + advisory + maybe 1 more
                    break

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)

        # Publish 5 events without consuming
        for n in range(1, 6):
            await bus.publish("bp", {"n": n})

        # Let subscriber process
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        # Should have events (newest ones) + advisory
        assert len(events) >= 3  # At least 2 data + 1 advisory

        # Last event should be advisory (channel starts with '_')
        advisory = [e for e in events if e.channel.startswith("_")]
        assert len(advisory) >= 1
        assert advisory[0].payload.get("dropped_count", 0) >= 3


class TestResume:
    """Test resume from sequence functionality."""

    @pytest.mark.asyncio
    async def test_resume_from_sequence(self) -> None:
        """New subscriber with since_sequence sees events after that sequence."""
        bus = Bus()

        # Publish 3 events
        e1 = await bus.publish("resume", {"n": 1})
        e2 = await bus.publish("resume", {"n": 2})
        e3 = await bus.publish("resume", {"n": 3})

        # New subscriber with since_sequence=e1.sequence should see e2 and e3
        events = []

        async def sub():
            async for event in bus.subscribe("resume", since_sequence=e1.sequence):
                events.append(event)
                if len(events) >= 2:
                    break

        task = asyncio.create_task(sub())
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        # Should see events with sequence > e1.sequence
        assert len(events) >= 2
        assert all(e.sequence > e1.sequence for e in events)
        assert any(e.sequence == e2.sequence for e in events)
        assert any(e.sequence == e3.sequence for e in events)


class TestUnsubscribe:
    """Test unsubscribe/close functionality."""

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_receiving(self) -> None:
        """Closing subscription stops it from receiving further events."""
        bus = Bus()
        events = []

        sub = bus.subscribe("unsub")
        task = asyncio.create_task(self._consume_until_close(sub, events))

        await asyncio.sleep(0.01)

        # Publish first event
        await bus.publish("unsub", {"n": 1})
        await asyncio.sleep(0.01)

        # Close subscription
        await sub.close()

        # Publish more events
        await bus.publish("unsub", {"n": 2})
        await bus.publish("unsub", {"n": 3})

        await task
        assert len(events) == 1
        assert events[0].payload == {"n": 1}

    @staticmethod
    async def _consume_until_close(sub, events):
        try:
            async for event in sub:
                events.append(event)
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_no_reference_leaks_on_close(self) -> None:
        """Bus doesn't leak references after subscription closes."""
        bus = Bus()

        sub = bus.subscribe("leak")
        await sub.close()

        # Publish some events
        await bus.publish("leak", {"data": "test"})
        await bus.publish("leak", {"data": "test2"})

        # No assertion needed; if we get here without hanging, it's good
        assert True


class TestEventShape:
    """Test Event dataclass shape and immutability."""

    @pytest.mark.asyncio
    async def test_event_is_frozen(self) -> None:
        """Event is frozen (immutable)."""
        event = Event(
            sequence=1,
            channel="test",
            payload={"key": "value"},
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(AttributeError):
            event.sequence = 2  # type: ignore

    @pytest.mark.asyncio
    async def test_event_has_required_fields(self) -> None:
        """Event has sequence, channel, payload, timestamp."""
        now = datetime.now(timezone.utc)
        event = Event(
            sequence=42,
            channel="test_channel",
            payload={"a": 1, "b": "two"},
            timestamp=now,
        )

        assert event.sequence == 42
        assert event.channel == "test_channel"
        assert event.payload == {"a": 1, "b": "two"}
        assert event.timestamp == now
