"""Plugin model for database storage."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base

PLUGIN_STATES = ("disabled", "enabled", "paused", "broken")


class Plugin(Base):
    """Plugin row in database.

    Stores installed plugins with their manifest, state, and capability
    acknowledgements.
    """

    __tablename__ = "plugins"

    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    version: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(32))
    manifest_json: Mapped[str] = mapped_column(Text)
    installed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    installed_by: Mapped[str] = mapped_column(String(36))
    disabled_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    capability_ack_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Plugin {self.id}@{self.version} ({self.state})>"
