"""create resume_profiles table

Revision ID: d7e3b1f9a6c2
Revises: c5d1a9e7b2f4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e3b1f9a6c2"
down_revision: Union[str, Sequence[str], None] = "c5d1a9e7b2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "resume_id", sa.Integer(),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("total_experience_years", sa.Float(), nullable=True),
        sa.Column("education", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("current_role", sa.String(length=255), nullable=True),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_resume_profiles_resume_id", "resume_profiles", ["resume_id"], unique=True)
    op.create_index("ix_resume_profiles_user_id", "resume_profiles", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_resume_profiles_user_id", table_name="resume_profiles")
    op.drop_index("ix_resume_profiles_resume_id", table_name="resume_profiles")
    op.drop_table("resume_profiles")
