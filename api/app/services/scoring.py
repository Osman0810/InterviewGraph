"""Deterministic competency and readiness calculations; no AI is used here."""

from dataclasses import dataclass
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import GapPriority, ScoreSource, SessionMode
from app.models.interview import Answer, Competency, CompetencyScore, Evaluation, InterviewSession, Question


FULL_INTERVIEW_COVERAGE = 3


@dataclass(frozen=True)
class CompetencyCalculation:
    interview_score: float | None
    resume_evidence_score: float
    final_score: float
    confidence: float
    gap_priority: GapPriority
    score_source: ScoreSource
    evaluated_answer_count: int


@dataclass(frozen=True)
class ReadinessCalculation:
    overall_readiness: float
    confidence: float
    score_source: ScoreSource


class ScoringService:
    """Owns transparent score math used by both interview modes."""

    @staticmethod
    def calculate_competency(
        *,
        importance: int,
        resume_evidence_score: float,
        resume_confidence: float,
        interview_scores: Iterable[float] = (),
        mode: SessionMode,
    ) -> CompetencyCalculation:
        if not 1 <= importance <= 5:
            raise ValueError("Competency importance must be between 1 and 5")
        resume_score = ScoringService._score(resume_evidence_score)
        evidence_confidence = ScoringService._unit(resume_confidence)
        evaluated_scores = [ScoringService._score(score) for score in interview_scores]

        if mode == SessionMode.RESUME_ONLY:
            final_score = resume_score
            interview_score = None
            confidence = evidence_confidence
            source = ScoreSource.RESUME_EVIDENCE
        elif evaluated_scores:
            interview_score = round(sum(evaluated_scores) / len(evaluated_scores), 2)
            final_score = round((0.75 * interview_score) + (0.25 * resume_score), 2)
            # Fewer than three evaluated answers means the interview sample is incomplete.
            coverage = min(len(evaluated_scores) / FULL_INTERVIEW_COVERAGE, 1.0)
            confidence = round((0.5 + (0.5 * evidence_confidence)) * (0.4 + (0.6 * coverage)), 2)
            source = ScoreSource.COMBINED
        else:
            # A started interview with no evaluated answer is still evidence-only, not a 75/25 claim.
            interview_score = None
            final_score = resume_score
            confidence = round(evidence_confidence * 0.4, 2)
            source = ScoreSource.RESUME_EVIDENCE

        return CompetencyCalculation(
            interview_score=interview_score,
            resume_evidence_score=resume_score,
            final_score=final_score,
            confidence=confidence,
            gap_priority=ScoringService.gap_priority(importance, final_score),
            score_source=source,
            evaluated_answer_count=len(evaluated_scores),
        )

    @staticmethod
    def calculate_overall(
        calculations: Iterable[tuple[int, CompetencyCalculation | CompetencyScore]], *, mode: SessionMode
    ) -> ReadinessCalculation:
        items = list(calculations)
        if not items:
            raise ValueError("At least one competency is required")
        if any(not 1 <= importance <= 5 for importance, _ in items):
            raise ValueError("Competency importance must be between 1 and 5")
        total_weight = sum(importance for importance, _ in items)
        readiness = round(sum(importance * result.final_score for importance, result in items) / total_weight, 2)
        confidence = round(sum(importance * result.confidence for importance, result in items) / total_weight, 2)
        source = ScoreSource.RESUME_EVIDENCE if mode == SessionMode.RESUME_ONLY else (
            ScoreSource.COMBINED if any(result.score_source == ScoreSource.COMBINED for _, result in items)
            else ScoreSource.RESUME_EVIDENCE
        )
        return ReadinessCalculation(readiness, confidence, source)

    @staticmethod
    def gap_priority(importance: int, competency_score: float) -> GapPriority:
        normalized_importance = importance / 5
        weighted_gap = (100 - ScoringService._score(competency_score)) * normalized_importance
        if weighted_gap >= 60:
            return GapPriority.CRITICAL
        if weighted_gap >= 36:
            return GapPriority.HIGH
        if weighted_gap >= 16:
            return GapPriority.MEDIUM
        return GapPriority.LOW

    def persist_session_scores(self, db: Session, session_id) -> ReadinessCalculation:
        """Upsert ORM score records from stored evidence and evaluated answers."""
        session = db.scalar(
            select(InterviewSession)
            .where(InterviewSession.id == session_id)
            .options(
                selectinload(InterviewSession.competencies).selectinload(Competency.resume_evidence),
                selectinload(InterviewSession.competencies).selectinload(Competency.score),
                selectinload(InterviewSession.competencies).selectinload(Competency.questions)
                .selectinload(Question.answer).selectinload(Answer.evaluation),
            )
        )
        if session is None or not session.competencies:
            raise ValueError("Session needs competencies before it can be scored")

        calculations: list[tuple[int, CompetencyCalculation]] = []
        for competency in session.competencies:
            if len(competency.resume_evidence) != 1:
                raise ValueError("Each competency needs exactly one résumé evidence record")
            evidence = competency.resume_evidence[0]
            evaluation_scores = [
                question.answer.evaluation.overall_score
                for question in competency.questions
                if question.answer is not None and question.answer.evaluation is not None
            ]
            calculation = self.calculate_competency(
                importance=competency.importance,
                resume_evidence_score=evidence.evidence_strength,
                resume_confidence=evidence.confidence,
                interview_scores=evaluation_scores,
                mode=session.mode,
            )
            self._persist_competency_score(db, competency, calculation)
            calculations.append((competency.importance, calculation))
        return self.calculate_overall(calculations, mode=session.mode)

    @staticmethod
    def _persist_competency_score(
        db: Session, competency: Competency, calculation: CompetencyCalculation
    ) -> None:
        score = competency.score or CompetencyScore(competency=competency)
        score.interview_score = calculation.interview_score
        score.resume_evidence_score = calculation.resume_evidence_score
        score.final_score = calculation.final_score
        score.confidence = calculation.confidence
        score.gap_priority = calculation.gap_priority
        score.score_source = calculation.score_source
        if score.id is None:
            db.add(score)

    @staticmethod
    def _score(value: float) -> float:
        return round(min(100.0, max(0.0, float(value))), 2)

    @staticmethod
    def _unit(value: float) -> float:
        return round(min(1.0, max(0.0, float(value))), 2)
