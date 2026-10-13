from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class VocabularyEntry:
    """A vocabulary item consisting of one term and one definition."""

    id: int
    term: str
    definition: str


@dataclass(slots=True)
class LearningProgress:
    """The current learning state of one vocabulary definition."""

    entry_id: int
    score: float = 0.0
    last_accessed: date | None = None


@dataclass(frozen=True, slots=True)
class StudyAttempt:
    """An immutable record of one answer submitted by the learner."""

    id: int
    entry_id: int
    is_correct: bool
    answered_at: datetime
    mode: str
