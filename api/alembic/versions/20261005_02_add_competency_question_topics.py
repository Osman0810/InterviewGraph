"""Add extracted question topics to competencies.

Revision ID: 20261005_02
Revises: 20261005_01
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261005_02"
down_revision: str | Sequence[str] | None = "20261005_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "competencies",
        sa.Column("question_topics", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("competencies", "question_topics")
