"""Store structured résumé evidence.

Revision ID: 20261005_03
Revises: 20261005_02
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261005_03"
down_revision: str | Sequence[str] | None = "20261005_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("resume_evidence") as batch_op:
        batch_op.alter_column(
            "evidence",
            existing_type=sa.Text(),
            type_=sa.JSON(),
            existing_nullable=True,
            nullable=False,
            server_default=sa.text("'[]'"),
            postgresql_using="CASE WHEN evidence IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(evidence) END",
        )
        batch_op.add_column(sa.Column("reasoning_summary", sa.Text(), nullable=True))
        batch_op.create_unique_constraint("uq_resume_evidence_competency", ["competency_id"])

    op.execute("UPDATE resume_evidence SET reasoning_summary = '' WHERE reasoning_summary IS NULL")
    with op.batch_alter_table("resume_evidence") as batch_op:
        batch_op.alter_column("reasoning_summary", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("resume_evidence") as batch_op:
        batch_op.drop_constraint("uq_resume_evidence_competency", type_="unique")
        batch_op.drop_column("reasoning_summary")
        batch_op.alter_column(
            "evidence",
            existing_type=sa.JSON(),
            type_=sa.Text(),
            existing_nullable=False,
            nullable=True,
            postgresql_using="evidence::text",
        )
