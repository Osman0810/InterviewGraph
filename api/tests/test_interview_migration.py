from io import StringIO
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import InterviewSession, Question
from app.models.enums import SessionMode, SessionStatus, QuestionType


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
