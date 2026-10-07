import importlib.util
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import InterviewSession, Question
from app.models.enums import SessionMode, SessionStatus, QuestionType


MIGRATION_05_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20261005_05_resume_evidence_score_source.py"
)


def _load_migration_05():
    spec = importlib.util.spec_from_file_location("migration_20261005_05", MIGRATION_05_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _EnumLabelResult:
    def __init__(self, labels: set[str]):
        self._labels = labels

    def scalars(self):
        return self

    def all(self):
        return list(self._labels)


class _MigrationBind:
    def __init__(self, dialect_name: str, labels: set[str]):
        self.dialect = SimpleNamespace(name=dialect_name)
        self._labels = labels

    def execute(self, _statement):
        return _EnumLabelResult(self._labels)


class _MigrationOp:
    def __init__(self, dialect_name: str, labels: set[str], *, offline: bool = False):
        self._bind = _MigrationBind(dialect_name, labels)
        self._offline = offline
        self.statements: list[str] = []

    def get_bind(self):
        return self._bind

    def get_context(self):
        return SimpleNamespace(as_sql=self._offline)

    def execute(self, statement):
        self.statements.append(str(statement))


def test_migration_preserves_existing_questions_and_matches_orm(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "20261005_03")
    engine = create_engine(url)
    sid, cid, qid = [uuid4() for _ in range(3)]
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO interview_sessions (id, status, mode) VALUES (:id, 'created', 'interview')"), {"id": sid.hex})
        connection.execute(text("""INSERT INTO competencies
            (id, session_id, name, category, description, importance, required_level, jd_evidence, question_topics)
            VALUES (:id, :sid, 'RAG', 'Generative AI', 'Retrieval', 5, 'advanced', 'RAG', '[]')"""),
            {"id": cid.hex, "sid": sid.hex})
        connection.execute(text("""INSERT INTO questions
            (id, session_id, competency_id, question_text, difficulty, question_type,
            sequence_number, expected_concepts, evaluation_rubric)
            VALUES (:id, :sid, :cid, 'Explain RAG', 'intermediate', 'practical', 1, '[]', '[]')"""),
            {"id": qid.hex, "sid": sid.hex, "cid": cid.hex})
    command.upgrade(cfg, "head")
    with Session(engine) as db:
        session = db.get(InterviewSession, sid)
        assert session.mode == SessionMode.INTERVIEW and session.status == SessionStatus.CREATED
        question = db.get(Question, qid)
        assert question.difficulty == 2 and question.question_type == QuestionType.IMPLEMENTATION
        assert not question.diagnostic
    command.downgrade(cfg, "20261005_03")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT difficulty FROM questions")).scalar() == "intermediate"
    command.upgrade(cfg, "head")
    engine.dispose()


def test_postgres_sql_creates_enums_once(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://test:test@localhost/test")
    output = StringIO()
    cfg = Config("alembic.ini", output_buffer=output)
    command.upgrade(cfg, "head", sql=True)
    sql = output.getvalue()
    assert sql.count("CREATE TYPE session_status") == 1
    assert sql.count("CREATE TYPE question_difficulty") == 1
    assert "interview_question_limit" in sql and "ck_question_difficulty" in sql
    assert "ALTER TYPE score_source RENAME VALUE" not in sql


def test_score_source_upgrade_skips_fresh_postgres_enum():
    migration = _load_migration_05()
    fake_op = _MigrationOp("postgresql", {"interview", "resume_evidence", "combined"})
    migration.op = fake_op

    migration.upgrade()

    assert fake_op.statements == []


def test_score_source_upgrade_renames_legacy_postgres_enum_label():
    migration = _load_migration_05()
    fake_op = _MigrationOp("postgresql", {"interview", "resume", "combined"})
    migration.op = fake_op

    migration.upgrade()

    assert fake_op.statements == [
        "ALTER TYPE score_source RENAME VALUE 'resume' TO 'resume_evidence'"
    ]


def test_score_source_downgrade_renames_only_when_legacy_label_is_absent():
    migration = _load_migration_05()
    fake_op = _MigrationOp("postgresql", {"interview", "resume_evidence", "combined"})
    migration.op = fake_op

    migration.downgrade()

    assert fake_op.statements == [
        "ALTER TYPE score_source RENAME VALUE 'resume_evidence' TO 'resume'"
    ]


def test_score_source_migration_leaves_non_postgresql_dialects_unchanged():
    migration = _load_migration_05()
    fake_op = _MigrationOp("sqlite", {"interview", "resume"})
    migration.op = fake_op

    migration.upgrade()
    migration.downgrade()

    assert fake_op.statements == []
