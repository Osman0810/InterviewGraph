from enum import Enum, IntEnum


class SessionStatus(str, Enum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionMode(str, Enum):
    INTERVIEW = "interview"
    RESUME_ONLY = "resume_only"


class ResumeFileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "text"


class QuestionDifficulty(IntEnum):
    FUNDAMENTALS = 1
    IMPLEMENTATION = 2
    DEBUGGING = 3
    ARCHITECTURE = 4


class QuestionType(str, Enum):
    CONCEPTUAL = "conceptual"
    IMPLEMENTATION = "implementation"
    DEBUGGING = "debugging"
    SCENARIO = "scenario"
    SYSTEM_DESIGN = "system_design"


class GapPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScoreSource(str, Enum):
    INTERVIEW = "interview"
    RESUME_EVIDENCE = "resume_evidence"
    COMBINED = "combined"
