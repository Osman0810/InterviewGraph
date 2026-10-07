from uuid import UUID

from pydantic import BaseModel

from app.ai.schemas.study_plan import StudyPlanOutput


class StudyPlanResponse(BaseModel):
    session_id: UUID
    plan: StudyPlanOutput
