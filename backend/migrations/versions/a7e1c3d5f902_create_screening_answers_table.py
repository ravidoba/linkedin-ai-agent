"""create screening_answers table

Revision ID: a7e1c3d5f902
Revises: 796c30a383fa
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7e1c3d5f902"
down_revision: Union[str, Sequence[str], None] = "796c30a383fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "screening_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("input_type", sa.String(length=50), nullable=False, server_default="text"),
        sa.Column("provenance", sa.String(length=50), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index(
        "ix_screening_answers_question_text",
        "screening_answers",
        ["question_text"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_screening_answers_question_text", table_name="screening_answers")
    op.drop_table("screening_answers")
