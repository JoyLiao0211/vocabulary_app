"""SQLite persistence and queries for the vocabulary application."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

from models import LearningProgress, StudyAttempt, VocabularyEntry

DB_FILE = Path(__file__).with_name("vocab.db")


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with row access and foreign keys enabled."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all required tables and indexes if they do not exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS vocabulary_entries (
                id INTEGER PRIMARY KEY,
                term TEXT NOT NULL,
                definition TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS learning_progress (
                entry_id INTEGER PRIMARY KEY,
                score REAL NOT NULL DEFAULT 0.0
                    CHECK(score >= 0.0 AND score <= 1.0),
                last_accessed TEXT,
                FOREIGN KEY(entry_id)
                    REFERENCES vocabulary_entries(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS study_attempts (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER NOT NULL,
                is_correct INTEGER NOT NULL
                    CHECK(is_correct IN (0, 1)),
                answered_at TEXT NOT NULL,
                mode TEXT NOT NULL,
                FOREIGN KEY(entry_id)
                    REFERENCES vocabulary_entries(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_vocabulary_term
                ON vocabulary_entries(term);

            CREATE INDEX IF NOT EXISTS idx_attempts_entry
                ON study_attempts(entry_id);

            CREATE INDEX IF NOT EXISTS idx_attempts_date
                ON study_attempts(answered_at);
            """)


def get_entry_count() -> int:
    """Return the total number of vocabulary entries."""
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM vocabulary_entries").fetchone()[0]


def get_entry(entry_id: int) -> VocabularyEntry | None:
    """Return one vocabulary entry by ID, or None if it does not exist."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, term, definition
            FROM vocabulary_entries
            WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()

    if row is None:
        return None

    return VocabularyEntry(
        id=row["id"],
        term=row["term"],
        definition=row["definition"],
    )


def get_progress(entry_id: int) -> LearningProgress:
    """Return the current progress for an entry, using defaults if absent."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO learning_progress (entry_id)
            VALUES (?)
            """,
            (entry_id,),
        )
        row = conn.execute(
            """
            SELECT entry_id, score, last_accessed
            FROM learning_progress
            WHERE entry_id = ?
            """,
            (entry_id,),
        ).fetchone()

    return LearningProgress(
        entry_id=row["entry_id"],
        score=row["score"],
        last_accessed=(
            date.fromisoformat(row["last_accessed"]) if row["last_accessed"] else None
        ),
    )


def get_entries_in_range(start: int, end: int) -> list[int]:
    """Return entry IDs in the half-open interval [start, end)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM vocabulary_entries
            WHERE id >= ? AND id < ?
            ORDER BY id
            """,
            (start, end),
        ).fetchall()

    return [row["id"] for row in rows]


def get_least_familiar_questions(
    start: int,
    end: int,
    number: int,
) -> list[int]:
    """Return entry IDs ordered from lowest to highest familiarity score."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT v.id
            FROM vocabulary_entries AS v
            LEFT JOIN learning_progress AS p
                ON p.entry_id = v.id
            WHERE v.id >= ? AND v.id < ?
            ORDER BY COALESCE(p.score, 0.0) ASC, v.id ASC
            LIMIT ?
            """,
            (start, end, number),
        ).fetchall()

    return [row["id"] for row in rows]


def get_least_familiar_and_last_accessed_questions(
    start: int,
    end: int,
    number: int,
) -> list[int]:
    """Prioritize low scores and entries not reviewed recently."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT v.id
            FROM vocabulary_entries AS v
            LEFT JOIN learning_progress AS p
                ON p.entry_id = v.id
            WHERE v.id >= ? AND v.id < ?
            ORDER BY
                COALESCE(p.score, 0.0)
                - 0.05 * MAX(
                    0.0,
                    julianday('now') -
                    julianday(
                        COALESCE(p.last_accessed, '1970-01-01')
                    )
                ) ASC,
                v.id ASC
            LIMIT ?
            """,
            (start, end, number),
        ).fetchall()

    return [row["id"] for row in rows]


def record_attempt(
    entry_id: int,
    is_correct: bool,
    mode: str,
    weight: float,
) -> StudyAttempt:
    """Record an answer and update its progress in one transaction."""
    if not 0.0 <= weight <= 1.0:
        raise ValueError("weight must be between 0 and 1")

    today = date.today().isoformat()
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    with get_connection() as conn:
        entry = conn.execute(
            "SELECT id FROM vocabulary_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()

        if entry is None:
            raise ValueError(f"Unknown vocabulary entry ID: {entry_id}")

        conn.execute(
            """
            INSERT OR IGNORE INTO learning_progress (entry_id)
            VALUES (?)
            """,
            (entry_id,),
        )

        cursor = conn.execute(
            """
            INSERT INTO study_attempts
                (entry_id, is_correct, answered_at, mode)
            VALUES (?, ?, ?, ?)
            """,
            (entry_id, int(is_correct), now, mode),
        )
        attempt_id = cursor.lastrowid

        conn.execute(
            """
            UPDATE learning_progress
            SET score = score * (1.0 - ?) + ? * ?,
                last_accessed = ?
            WHERE entry_id = ?
            """,
            (weight, int(is_correct), weight, today, entry_id),
        )

    return StudyAttempt(
        id=attempt_id,
        entry_id=entry_id,
        is_correct=is_correct,
        answered_at=datetime.fromisoformat(now),
        mode=mode,
    )


def get_attempts(entry_id: int) -> list[StudyAttempt]:
    """Return all recorded attempts for one entry in chronological order."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, entry_id, is_correct, answered_at, mode
            FROM study_attempts
            WHERE entry_id = ?
            ORDER BY answered_at, id
            """,
            (entry_id,),
        ).fetchall()

    return [
        StudyAttempt(
            id=row["id"],
            entry_id=row["entry_id"],
            is_correct=bool(row["is_correct"]),
            answered_at=datetime.fromisoformat(row["answered_at"]),
            mode=row["mode"],
        )
        for row in rows
    ]


def get_random_distractor_terms(
    correct_term: str,
    number: int,
) -> list[str]:
    """Return distinct random terms other than the correct answer."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT term
            FROM vocabulary_entries
            WHERE term != ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (correct_term, number),
        ).fetchall()

    return [row["term"] for row in rows]
