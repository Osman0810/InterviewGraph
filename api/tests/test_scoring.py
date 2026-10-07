import pytest

from app.models.enums import GapPriority, ScoreSource, SessionMode
from app.services.scoring import ScoringService


def test_interview_score_uses_fixed_75_25_weighting():
    result = ScoringService.calculate_competency(
        importance=5,
        resume_evidence_score=40,
        resume_confidence=.8,
        interview_scores=[80, 100],
        mode=SessionMode.INTERVIEW,
    )

    assert result.interview_score == 90
    assert result.final_score == 77.5
    assert result.score_source == ScoreSource.COMBINED
    assert result.gap_priority == GapPriority.MEDIUM


def test_low_interview_coverage_reduces_confidence_without_changing_formula():
    one_answer = ScoringService.calculate_competency(
        importance=3, resume_evidence_score=60, resume_confidence=.8,
        interview_scores=[80], mode=SessionMode.INTERVIEW,
    )
    three_answers = ScoringService.calculate_competency(
        importance=3, resume_evidence_score=60, resume_confidence=.8,
        interview_scores=[80, 80, 80], mode=SessionMode.INTERVIEW,
    )

    assert one_answer.final_score == three_answers.final_score == 75
    assert one_answer.confidence == .54
    assert three_answers.confidence == .9


def test_interview_without_evaluations_is_not_presented_as_interview_measurement():
    result = ScoringService.calculate_competency(
        importance=4, resume_evidence_score=70, resume_confidence=.8,
        interview_scores=[], mode=SessionMode.INTERVIEW,
    )

    assert result.interview_score is None
    assert result.final_score == 70
    assert result.confidence == .32
    assert result.score_source == ScoreSource.RESUME_EVIDENCE


def test_resume_only_uses_evidence_score_and_source_exactly():
    result = ScoringService.calculate_competency(
        importance=5, resume_evidence_score=42, resume_confidence=.65,
        interview_scores=[100], mode=SessionMode.RESUME_ONLY,
    )

    assert result.interview_score is None
    assert result.final_score == 42
    assert result.confidence == .65
    assert result.score_source == ScoreSource.RESUME_EVIDENCE


@pytest.mark.parametrize(
    ("importance", "score", "expected"),
    [
        (5, 0, GapPriority.CRITICAL),
        (5, 64, GapPriority.HIGH),
        (3, 60, GapPriority.MEDIUM),
        (1, 90, GapPriority.LOW),
    ],
)
def test_gap_priority_weights_weakness_by_normalized_jd_importance(importance, score, expected):
    assert ScoringService.gap_priority(importance, score) == expected


def test_overall_readiness_is_importance_weighted_and_deterministic():
    python = ScoringService.calculate_competency(
        importance=5, resume_evidence_score=50, resume_confidence=.8,
        interview_scores=[90, 90, 90], mode=SessionMode.INTERVIEW,
    )
    testing = ScoringService.calculate_competency(
        importance=1, resume_evidence_score=20, resume_confidence=.4,
        interview_scores=[20, 20, 20], mode=SessionMode.INTERVIEW,
    )

    overall = ScoringService.calculate_overall([(5, python), (1, testing)], mode=SessionMode.INTERVIEW)

    assert overall.overall_readiness == 70
    assert overall.confidence == 0.87
    assert overall.score_source == ScoreSource.COMBINED


def test_invalid_input_is_rejected_deterministically():
    with pytest.raises(ValueError, match="importance"):
        ScoringService.calculate_competency(
            importance=0, resume_evidence_score=50, resume_confidence=.5, mode=SessionMode.INTERVIEW
        )
    with pytest.raises(ValueError, match="At least one"):
        ScoringService.calculate_overall([], mode=SessionMode.RESUME_ONLY)
