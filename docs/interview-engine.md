# Adaptive interview engine

The pure InterviewEngine in api/app/services/interview_engine.py takes competency
states and ordered question history. It has no database, Gemini, or FastAPI dependency.
Scores are on a 0–100 scale; skipped answers count as zero. Missing evaluations block
advancement.

## Policy

- Reserve first-pass coverage for the highest-importance competencies that fit in
  the question budget. Within equal importance, less résumé evidence gets priority.
  Résumé evidence never establishes verified skill.
- Start each competency at fundamentals (1).
- Scores of 80 or more increase difficulty by one, up to architecture (4).
  Scores below 50 decrease difficulty by one, down to fundamentals.
- Important competencies (importance 4–5) may receive an immediate follow-up,
  provided enough slots remain for coverage and the last two questions were not
  already on that competency.
- Allow one diagnostic per competency. A failed diagnostic retires that competency.
- After initial coverage, prioritize importance squared, discounted by questions
  already asked. Résumé uncertainty and previous weakness contribute smaller weights.
- Question types follow difficulty: conceptual, implementation, debugging/scenario,
  system_design. At level 3 the less-used type is selected.
- Stop after the configured question budget has been answered/evaluated, or earlier
  when no eligible competencies remain.

INTERVIEW_QUESTION_LIMIT defaults to 12 (range 1–100). The value is saved when a
session starts, so changing configuration does not change an active interview.

## API

POST /sessions/{id}/interview/start starts an analyzed session and returns the first
question. Repeating it returns the current question without restarting.

GET /sessions/{id}/interview/next-question returns the unanswered question, waits
for evaluation, or generates and persists the next question. Responses are marked
Cache-Control: no-store. Status is in_progress, awaiting_evaluation, or completed.
The question is null for waiting/completed responses.

Public question fields: id, competency_id, competency, question, difficulty, type,
sequence_number. Expected concepts and evaluation rubrics remain backend-only.

The service locks the session row during advancement on PostgreSQL, preventing
concurrent start/next requests from generating separate questions. The database
also enforces unique sequence numbers per session. SQLite tests verify sequential
behavior; SQLite does not provide PostgreSQL row-lock concurrency guarantees.

## Gemini boundary

The shared Gemini provider generates only question wording, expected concepts and
a rubric. It must echo the application-selected competency, difficulty and type;
mismatches and exact normalized repeats are rejected. Prior questions are provided
to discourage semantic repetition. No new client is constructed by the engine or
question service. Generation failures roll back session changes.

This increment consumes persisted Answer and Evaluation records. Answer submission,
evaluation generation and the interview screen remain separate workflows.

## Migration and verification

Run alembic upgrade head from api/ with the configured PostgreSQL database.
Revision 20261005_04 converts legacy question difficulty to integers, maps
practical/coding to implementation, and adds the question budget and diagnostic flag.
The existing initial migration's duplicate enum creation and ORM enum value mismatch
were corrected so fresh PostgreSQL databases use the same lower-case values.

Tests cover independent policy decisions, mocked question generation, persistence,
private-field filtering, idempotence, waiting/completion, rollback, and migration
upgrade/downgrade with existing questions. Live PostgreSQL concurrency is not
covered by the SQLite suite.
