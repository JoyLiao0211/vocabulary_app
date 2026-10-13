"""Data models for vocabulary entries and study progress."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class VocabularyEntry:
    """Represent one term-definition pair with a unique ID."""

    id: int
    term: str
    definition: str


@dataclass(slots=True)
class LearningProgress:
    """Represent the current learning state of one vocabulary entry."""

    entry_id: int
    score: float = 0.0
    last_accessed: date | None = None


@dataclass(frozen=True, slots=True)
class StudyAttempt:
    """Represent an immutable record of a submitted answer."""

    id: int
    entry_id: int
    is_correct: bool
    answered_at: datetime
    mode: str
