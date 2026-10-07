"""Deterministic interview policy. No HTTP, database, or AI dependencies."""
from dataclasses import dataclass
from uuid import UUID

from app.models.enums import QuestionType


@dataclass(frozen=True)
class CompetencyState:
    id: UUID
    name: str
    importance: int
    resume_evidence: int = 0


@dataclass(frozen=True)
class AskedQuestion:
    competency_id: UUID
    difficulty: int
    question_type: QuestionType
    score: float | None
    diagnostic: bool = False


@dataclass(frozen=True)
class QuestionPlan:
    competency_id: UUID
    difficulty: int
    question_type: QuestionType
    diagnostic: bool = False


class InterviewEngine:
    """Scores are 0–100; unanswered/unevaluated questions block advancement."""

    def __init__(self, question_limit: int = 12):
        if not 1 <= question_limit <= 100:
            raise ValueError("Question limit must be between 1 and 100")
        self.question_limit = question_limit

    def next_plan(
        self, competencies: list[CompetencyState], history: list[AskedQuestion]
    ) -> QuestionPlan | None:
        if any(q.score is None for q in history):
            raise ValueError("Awaiting answer evaluation")
        if len(history) >= self.question_limit or not competencies:
            return None

        by_id = {c.id: c for c in competencies}
        groups = {c.id: [q for q in history if q.competency_id == c.id] for c in competencies}
        # Reserve a first pass through the most important competencies that fit.
        targets = sorted(competencies, key=lambda c: (-c.importance, c.resume_evidence, str(c.id)))[:self.question_limit]
        uncovered = [c for c in targets if not groups[c.id]]
        remaining = self.question_limit - len(history)
        last = history[-1] if history else None

        # One immediate probe on an important topic, only if coverage still fits.
        if last and last.competency_id in by_id and remaining > len(uncovered):
            c = by_id[last.competency_id]
            previous = groups[c.id]
            consecutive = len(history) > 1 and history[-2].competency_id == c.id
            if c.importance >= 4 and not consecutive and not last.diagnostic:
                if last.score < 50 and not any(q.diagnostic for q in previous):
                    return self._plan(c, previous, diagnostic=True)
                if last.score >= 80 and last.difficulty < 4:
                    return self._plan(c, previous)

        if uncovered:
            chosen = uncovered[0]
        else:
            # Diminishing returns and importance-squared favor high-priority topics.
            # A failed diagnostic retires a topic for the remainder of this session.
            candidates = [
                c for c in competencies
                if not any(q.diagnostic and q.score < 50 for q in groups[c.id])
            ]
            if not candidates:
                return None
            def priority(c: CompetencyState) -> float:
                previous = groups[c.id]
                performance = previous[-1].score if previous else 50
                uncertainty = (100 - c.resume_evidence) / 100
                weakness = (100 - performance) / 100
                return c.importance ** 2 * (1 + .2 * uncertainty + .2 * weakness) / (len(previous) + 1) ** 2
            chosen = sorted(candidates, key=lambda c: (-priority(c), str(c.id)))[0]
        return self._plan(chosen, groups[chosen.id])

    @staticmethod
    def _plan(c: CompetencyState, previous: list[AskedQuestion], diagnostic=False) -> QuestionPlan:
        # Résumé evidence affects priority, never substitutes for demonstrated skill.
        difficulty = 1
        if previous:
            last = previous[-1]
            difficulty = max(1, min(4, last.difficulty + (1 if last.score >= 80 else -1 if last.score < 50 else 0)))
        types = {
            1: [QuestionType.CONCEPTUAL],
            2: [QuestionType.IMPLEMENTATION],
            3: [QuestionType.DEBUGGING, QuestionType.SCENARIO],
            4: [QuestionType.SYSTEM_DESIGN],
        }[difficulty]
        counts = {t: sum(q.question_type == t for q in previous) for t in types}
        question_type = min(types, key=lambda t: counts[t])
        return QuestionPlan(c.id, difficulty, question_type, diagnostic)
