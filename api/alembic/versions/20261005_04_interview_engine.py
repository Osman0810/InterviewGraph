"""Numeric question difficulty and adaptive interview state."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_04"
down_revision = "20261005_03"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("interview_sessions", sa.Column("interview_question_limit", sa.Integer(), nullable=True))
    # Add-and-copy works with PostgreSQL enums and SQLite VARCHAR representations.
    op.add_column("questions", sa.Column("difficulty_number", sa.Integer(), nullable=True))
    op.add_column("questions", sa.Column("type_name", sa.String(14), nullable=True))
    op.execute("""UPDATE questions SET difficulty_number = CASE lower(CAST(difficulty AS VARCHAR))
        WHEN 'beginner' THEN 1 WHEN 'intermediate' THEN 2 WHEN 'advanced' THEN 3 END""")
    op.execute("""UPDATE questions SET type_name = CASE lower(CAST(question_type AS VARCHAR))
        WHEN 'practical' THEN 'implementation' WHEN 'coding' THEN 'implementation'
        ELSE lower(CAST(question_type AS VARCHAR)) END""")
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("difficulty")
        batch.drop_column("question_type")
        batch.alter_column("difficulty_number", new_column_name="difficulty", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("type_name", new_column_name="question_type", existing_type=sa.String(14), nullable=False)
        batch.add_column(sa.Column("diagnostic", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_check_constraint("ck_question_difficulty", "difficulty BETWEEN 1 AND 4")


def downgrade():
    # Collapses architecture to the previous highest level; preserves all questions.
    op.add_column("questions", sa.Column("difficulty_old", sa.String(12), nullable=True))
    op.add_column("questions", sa.Column("type_old", sa.String(10), nullable=True))
    op.execute("""UPDATE questions SET difficulty_old = CASE difficulty
        WHEN 1 THEN 'beginner' WHEN 2 THEN 'intermediate' ELSE 'advanced' END""")
    op.execute("""UPDATE questions SET type_old = CASE question_type
        WHEN 'conceptual' THEN 'conceptual' WHEN 'implementation' THEN 'practical'
        ELSE 'scenario' END""")
    with op.batch_alter_table("questions") as batch:
        batch.drop_constraint("ck_question_difficulty", type_="check")
        batch.drop_column("difficulty")
        batch.drop_column("question_type")
        batch.drop_column("diagnostic")
        batch.alter_column("difficulty_old", new_column_name="difficulty", existing_type=sa.String(12), nullable=False)
        batch.alter_column("type_old", new_column_name="question_type", existing_type=sa.String(10), nullable=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE questions ALTER COLUMN difficulty TYPE question_difficulty USING difficulty::question_difficulty")
        op.execute("ALTER TABLE questions ALTER COLUMN question_type TYPE question_type USING question_type::question_type")
    op.drop_column("interview_sessions", "interview_question_limit")
