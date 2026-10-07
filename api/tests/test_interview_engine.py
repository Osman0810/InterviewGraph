from uuid import UUID
import pytest
from app.models.enums import QuestionType as T
from app.services.interview_engine import InterviewEngine, CompetencyState, AskedQuestion


def c(n=1, importance=5, evidence=0):
    return CompetencyState(UUID(int=n), f"Skill {n}", importance, evidence)


def answered(plan, score):
    return AskedQuestion(plan.competency_id, plan.difficulty, plan.question_type, score, plan.diagnostic)


def test_strong_rag_answers_advance_through_four_levels():
    engine = InterviewEngine()
    history = []
    for level in range(1, 5):
        plan = engine.next_plan([c()], history)
        assert plan.difficulty == level
        history.append(answered(plan, 90))
    assert plan.question_type == T.SYSTEM_DESIGN


def test_one_diagnostic_then_moves_to_another_topic():
    engine = InterviewEngine()
    states = [c(), c(2, 4)]
    first = engine.next_plan(states, [])
    diagnostic = engine.next_plan(states, [answered(first, 20)])
    assert diagnostic.competency_id == first.competency_id
    assert diagnostic.diagnostic and diagnostic.difficulty == 1
    history = [answered(first, 20), answered(diagnostic, 20)]
    assert engine.next_plan(states, history).competency_id == c(2).id
    # Failed diagnostic retires the topic even after remaining topics are covered.
    history.append(answered(engine.next_plan(states, history), 60))
    assert engine.next_plan(states, history).competency_id == c(2).id


def test_low_priority_receives_fewer_questions_and_coverage_is_reserved():
    engine = InterviewEngine(12)
    states = [c(), c(2, 3), c(3, 1)]
    history = []
    for _ in range(12):
        history.append(answered(engine.next_plan(states, history), 65))
    counts = [sum(q.competency_id == s.id for q in history) for s in states]
    assert counts[0] > counts[1] > counts[2] >= 1
    assert engine.next_plan(states, history) is None


def test_short_interview_covers_highest_priorities():
    states = [c(), c(2, 4), c(3, 1)]
    engine = InterviewEngine(2)
    first = engine.next_plan(states, [])
    second = engine.next_plan(states, [answered(first, 95)])
    assert second.competency_id == states[1].id


def test_evidence_changes_priority_but_does_not_prove_knowledge():
    states = [c(1, 5, 90), c(2, 5, 10)]
    plan = InterviewEngine().next_plan(states, [])
    assert plan.competency_id == states[1].id
    assert plan.difficulty == 1


def test_medium_score_keeps_level_and_varies_type():
    history = [AskedQuestion(c().id, 3, T.DEBUGGING, 60)]
    plan = InterviewEngine().next_plan([c()], history)
    assert plan.difficulty == 3 and plan.question_type == T.SCENARIO


def test_pending_answer_blocks_advancement():
    with pytest.raises(ValueError, match="evaluation"):
        InterviewEngine().next_plan([c()], [AskedQuestion(c().id, 1, T.CONCEPTUAL, None)])


def test_no_candidates_and_config_limits():
    assert InterviewEngine().next_plan([], []) is None
    for limit in [0, 101]:
        with pytest.raises(ValueError):
            InterviewEngine(limit)
