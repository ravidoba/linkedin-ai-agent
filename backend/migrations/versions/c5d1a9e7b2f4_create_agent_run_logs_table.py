"""create agent_run_logs table

Revision ID: c5d1a9e7b2f4
Revises: b3f8e2a1c4d7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d1a9e7b2f4"
down_revision: Union[str, Sequence[str], None] = "b3f8e2a1c4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_run_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id", sa.Integer(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("step", sa.String(length=100), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=True),
        sa.Column("job_number", sa.Integer(), nullable=True),
        sa.Column("job_total", sa.Integer(), nullable=True),
        sa.Column("linkedin_job_id", sa.String(length=100), nullable=True),
        sa.Column("job_title", sa.String(length=500), nullable=True),
        sa.Column("job_company", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_agent_run_logs_run_id", "agent_run_logs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_run_logs_run_id", table_name="agent_run_logs")
    op.drop_table("agent_run_logs")
