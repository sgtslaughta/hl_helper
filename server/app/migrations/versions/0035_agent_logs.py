"""agent logs + policies

Revision ID: 0035_agent_logs
Revises: 0034_host_advisory_exposure
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_agent_logs"
down_revision = "0034_host_advisory_exposure"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "agent_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("host_id", sa.Text, nullable=False),
        sa.Column("agent_id", sa.Text, nullable=False),
        sa.Column("agent_session_id", sa.Text, nullable=False),
        sa.Column("agent_version", sa.Text),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.SmallInteger, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("outcome", sa.SmallInteger),
        sa.Column("duration_ns", sa.BigInteger),
        sa.Column("message", sa.Text),
        sa.Column("labels", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("details", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error", sa.JSON),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("agent_session_id", "seq", name="uq_agent_logs_session_seq"),
    )
    op.create_index("ix_logs_host_ts", "agent_logs", ["host_id", sa.text("ts DESC")])
    op.create_index("ix_logs_action", "agent_logs", ["action", sa.text("ts DESC")])
    op.create_index("ix_logs_level", "agent_logs", ["level", sa.text("ts DESC")])
    if is_pg:
        op.execute("CREATE INDEX ix_logs_outcome ON agent_logs(outcome, ts DESC) WHERE outcome IS NOT NULL")
        op.execute("CREATE INDEX ix_logs_labels_gin  ON agent_logs USING gin (labels)")
        op.execute("CREATE INDEX ix_logs_details_gin ON agent_logs USING gin (details)")

    op.create_table(
        "agent_log_policies",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("policy_json", sa.JSON, nullable=False),
        sa.Column("policy_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scope", name="uq_log_policy_scope"),
    )


def downgrade():
    op.drop_table("agent_log_policies")
    op.drop_table("agent_logs")
