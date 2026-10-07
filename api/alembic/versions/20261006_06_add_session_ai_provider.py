"""Add provider and model pins to interview sessions."""

import sqlalchemy as sa
from alembic import op


revision = "20261006_06"
down_revision = "20261005_05"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("interview_sessions", sa.Column("ai_provider", sa.String(length=50), nullable=True))
    op.add_column("interview_sessions", sa.Column("ai_model", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("interview_sessions", "ai_model")
    op.drop_column("interview_sessions", "ai_provider")
