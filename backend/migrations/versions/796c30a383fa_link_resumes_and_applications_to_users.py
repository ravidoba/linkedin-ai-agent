
"""link resumes and applications to users

Revision ID: 796c30a383fa
Revises: 0b0979c7fa3e
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "796c30a383fa"
down_revision: Union[str, Sequence[str], None] = "0b0979c7fa3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_applications_user_id",
        "applications",
        ["user_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_applications_user_id",
        "applications",
        "users",
        ["user_id"],
        ["id"],
    )

    op.add_column(
        "resumes",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_resumes_user_id",
        "resumes",
        ["user_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_resumes_user_id",
        "resumes",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_resumes_user_id",
        "resumes",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_resumes_user_id",
        table_name="resumes",
    )

    op.drop_column("resumes", "user_id")

    op.drop_constraint(
        "fk_applications_user_id",
        "applications",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_applications_user_id",
        table_name="applications",
    )

    op.drop_column("applications", "user_id")
