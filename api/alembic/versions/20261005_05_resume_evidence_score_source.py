"""Rename the evidence-only score source for clearer client semantics."""

import sqlalchemy as sa
from alembic import op


revision = "20261005_05"
down_revision = "20261005_04"
branch_labels = None
depends_on = None


def _score_source_labels() -> set[str] | None:
    """Return PostgreSQL ``score_source`` labels, or None when they are unavailable.

    Offline SQL generation has no database catalog to inspect. Leaving the enum
    untouched in that mode is intentional: the initial migration already creates
    the current ``resume_evidence`` label for a fresh schema.
    """

    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or op.get_context().as_sql:
        return None

    return set(
        bind.execute(
            sa.text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'score_source'::regtype"
            )
        )
        .scalars()
        .all()
    )


def upgrade():
    labels = _score_source_labels()
    if labels is not None and "resume" in labels and "resume_evidence" not in labels:
        op.execute("ALTER TYPE score_source RENAME VALUE 'resume' TO 'resume_evidence'")


def downgrade():
    labels = _score_source_labels()
    if labels is not None and "resume_evidence" in labels and "resume" not in labels:
        op.execute("ALTER TYPE score_source RENAME VALUE 'resume_evidence' TO 'resume'")
