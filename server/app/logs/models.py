"""SQLAlchemy ORM models for agent logging."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    JSON,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)

from server.app.models.base import Base


class AgentLog(Base):
    """Agent log entry in Elastic Common Schema format."""

    __tablename__ = "agent_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    host_id = Column(Text, nullable=False)
    agent_id = Column(Text, nullable=False)
    agent_session_id = Column(Text, nullable=False)
    agent_version = Column(Text)
    seq = Column(BigInteger, nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    level = Column(SmallInteger, nullable=False)
    action = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    outcome = Column(SmallInteger)
    duration_ns = Column(BigInteger)
    message = Column(Text)
    labels = Column(JSON, nullable=False, default=dict)
    details = Column(JSON, nullable=False, default=dict)
    error = Column(JSON)
    ingested_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("agent_session_id", "seq", name="uq_agent_logs_session_seq"),
    )


class AgentLogPolicy(Base):
    """Policy configuration for agent log collection."""

    __tablename__ = "agent_log_policies"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scope = Column(Text, nullable=False, unique=True)
    policy_json = Column(JSON, nullable=False)
    policy_version = Column(Integer, nullable=False, default=1)
    expires_at = Column(DateTime(timezone=True))
    created_by = Column(Text)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
