"""Focused provider-backed study-plan generation from persisted gap signals."""

from collections import defaultdict
from threading import Lock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.provider import AIProvider
from app.ai.prompts.study_plan import build_study_plan_prompt
from app.ai.schemas.study_plan import StudyPlanOutput
from app.models.interview import Answer, Competency, InterviewSession, Question, StudyPlan


class StudyPlanNotFound(ValueError):
    pass


class StudyPlanConflict(ValueError):
    pass


class StudyPlanService:
    _locks: defaultdict[UUID, Lock] = defaultdict(Lock)

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def generate(self, db: Session, session_id: UUID, *, regenerate: bool) -> StudyPlanOutput:
        lock = self._locks[session_id]
        if not lock.acquire(blocking=False):
            raise StudyPlanConflict("Study-plan generation is already in progress")
        try:
            return self._generate_locked(db, session_id, regenerate=regenerate)
        finally:
            lock.release()

    def _generate_locked(self, db: Session, session_id: UUID, *, regenerate: bool) -> StudyPlanOutput:
        try:
            session = db.scalar(
                select(InterviewSession).where(InterviewSession.id == session_id).options(
                    selectinload(InterviewSession.competencies).selectinload(Competency.score),
                    selectinload(InterviewSession.competencies).selectinload(Competency.resume_evidence),
                    selectinload(InterviewSession.competencies).selectinload(Competency.questions).selectinload(Question.answer).selectinload(Answer.evaluation),
                    selectinload(InterviewSession.study_plan),
                ).with_for_update()
            )
            if session is None:
                raise StudyPlanNotFound("Session not found")
            if not session.competencies or any(item.score is None for item in session.competencies):
                raise StudyPlanConflict("Calculate results before generating a study plan")
            if session.study_plan is not None and not regenerate:
                return StudyPlanOutput.model_validate(session.study_plan.generated_plan)

            output = self._provider.generate_structured(
                prompt=build_study_plan_prompt(gaps=self._signals(session)), response_schema=StudyPlanOutput
            )
            self._validate_groups(output)
            serialized = output.model_dump(mode="json")
            if session.study_plan is None:
                session.study_plan = StudyPlan(
                    generated_plan=serialized,
                    ai_provider=self._provider.provider_name,
                    model_name=self._provider.model_name,
                    structured_result=serialized,
                )
            else:
                session.study_plan.generated_plan = serialized
                session.study_plan.ai_provider = self._provider.provider_name
                session.study_plan.model_name = self._provider.model_name
                session.study_plan.structured_result = serialized
            db.commit()
            return output
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _signals(session: InterviewSession) -> list[dict[str, object]]:
        signals = []
        for competency in sorted(session.competencies, key=lambda item: (-item.importance, item.score.final_score)):
            evidence = competency.resume_evidence[0] if competency.resume_evidence else None
            missing = sorted({concept for question in competency.questions if question.answer is not None and question.answer.evaluation is not None for concept in question.answer.evaluation.missing_concepts})
            score = competency.score
            signals.append({"competency": competency.name, "jd_importance": competency.importance,
                            "competency_score": score.final_score, "gap_priority": score.gap_priority.value,
                            "weak_resume_evidence": evidence is None or evidence.evidence_strength < 61,
                            "resume_evidence_score": evidence.evidence_strength if evidence else 0,
                            "missing_interview_concepts": missing})
        return signals

    @staticmethod
    def _validate_groups(output: StudyPlanOutput) -> None:
        for group, expected_priority in ((output.critical, "Critical"), (output.important, "Important"), (output.optional, "Optional")):
            if any(topic.priority != expected_priority for topic in group):
                raise StudyPlanConflict("Study plan topics must match their priority group")
