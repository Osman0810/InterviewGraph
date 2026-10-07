"""Rename the evidence-only score source for clearer client semantics."""

from alembic import op


revision = "20261005_05"
down_revision = "20261005_04"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE score_source RENAME VALUE 'resume' TO 'resume_evidence'")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE score_source RENAME VALUE 'resume_evidence' TO 'resume'")
