"""One-time migration from the legacy CSV format to SQLite."""

import csv
from pathlib import Path

from database import get_connection, init_db

DATA_FILE = Path(__file__).with_name("data.csv")


def migrate_csv() -> int:
    """Import legacy entries and their per-definition progress into SQLite."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"CSV file not found: {DATA_FILE}")

    init_db()

    with get_connection() as conn:
        existing_count = conn.execute(
            "SELECT COUNT(*) FROM vocabulary_entries"
        ).fetchone()[0]

        if existing_count:
            raise RuntimeError(
                "The database already contains vocabulary entries. "
                "Use an empty database for migration."
            )

    migrated_count = 0

    with DATA_FILE.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        reader = csv.DictReader(file)

        required_columns = {
            "ID",
            "Term",
            "NewDefinition",
            "Scores",
            "AccessTime",
        }

        if not required_columns.issubset(reader.fieldnames or []):
            raise ValueError(
                f"CSV must contain these columns: {sorted(required_columns)}"
            )

        with get_connection() as conn:
            for row in reader:
                term = row["Term"].strip()
                definitions = row["NewDefinition"].splitlines()
                score_lines = row["Scores"].splitlines()
                access_times = row["AccessTime"].splitlines()

                if not term:
                    raise ValueError(f"Missing term in legacy row {row['ID']}")

                if not (len(definitions) == len(score_lines) == len(access_times)):
                    raise ValueError(
                        f"Definition, score, and date counts do not match "
                        f"for legacy ID {row['ID']}"
                    )

                if not definitions:
                    raise ValueError(f"No definitions found for legacy ID {row['ID']}")

                for definition, score_text, accessed in zip(
                    definitions,
                    score_lines,
                    access_times,
                ):
                    definition = definition.strip()

                    if not definition:
                        raise ValueError(f"Empty definition in legacy ID {row['ID']}")

                    score = float(score_text)

                    if not 0.0 <= score <= 1.0:
                        raise ValueError(
                            f"Score out of range for legacy ID {row['ID']}"
                        )

                    if accessed:
                        from datetime import date

                        date.fromisoformat(accessed)

                    cursor = conn.execute(
                        """
                        INSERT INTO vocabulary_entries (term, definition)
                        VALUES (?, ?)
                        """,
                        (term, definition),
                    )

                    entry_id = cursor.lastrowid

                    conn.execute(
                        """
                        INSERT INTO learning_progress
                            (entry_id, score, last_accessed)
                        VALUES (?, ?, ?)
                        """,
                        (entry_id, score, accessed or None),
                    )

                    migrated_count += 1

    return migrated_count


if __name__ == "__main__":
    count = migrate_csv()
    print(f"Migration completed: {count} vocabulary entries imported.")
