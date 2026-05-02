"""Tests for Notification, Webhook, and Setting models."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.models import Notification, Webhook, Setting


@pytest.mark.asyncio
async def test_notification_unique_name(sm):
    """Test that notification names are unique."""
    async with sm() as session:
        n1 = Notification(
            id="n-1",
            name="ops",
            provider="slack",
            config={"webhook_url": "ref:slack-1"},
        )
        session.add(n1)
        await session.commit()

        n2 = Notification(
            id="n-2", name="ops", provider="discord", config={}
        )
        session.add(n2)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_webhook_events_list(sm):
    """Test that webhook events are stored and retrieved as a list."""
    async with sm() as session:
        w = Webhook(
            id="w-1",
            name="ci",
            url="https://ci.example/hook",
            events=["task.completed", "host.offline"],
            hmac_secret_ref="ref:hmac-w-1",
        )
        session.add(w)
        await session.commit()

        got = await session.scalar(
            select(Webhook).where(Webhook.id == "w-1")
        )
        assert got.events == ["task.completed", "host.offline"]
        assert got.enabled is True


@pytest.mark.asyncio
async def test_setting_pk_is_key(sm):
    """Test that Setting uses key as primary key."""
    async with sm() as session:
        s = Setting(
            key="grpc.endpoint",
            value="grpc.example:443",
            source="env",
            scope="env-locked",
        )
        session.add(s)
        await session.commit()

        got = await session.scalar(
            select(Setting).where(Setting.key == "grpc.endpoint")
        )
        assert got.value == "grpc.example:443"
        assert got.scope == "env-locked"
