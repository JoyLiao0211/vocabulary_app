# AGENTS.md

## Project purpose

This repository is a small Flask vocabulary-study app. It presents vocabulary cards, multiple-choice questions, and spelling practice using a SQLite database and session-based progress tracking.

## Key files

- [app.py](app.py): Flask routes and study-session logic.
- [database.py](database.py): SQLite schema, queries, and progress tracking.
- [models.py](models.py): dataclasses for vocabulary entries, learning progress, and study attempts.
- [migrate_csv.py](migrate_csv.py): one-off CSV-import workflow for legacy data.
- [templates/](templates/): Jinja templates for study pages.
- [static/](static/): CSS and static assets.
- [README.md](README.md): project-level notes.

## Development conventions

- Keep database schema changes in sync with the dataclasses in [models.py](models.py) and the queries in [database.py](database.py).
- Prefer small, well-scoped edits in the existing Flask route structure instead of introducing a new framework or architecture.
- The app uses `session` heavily to persist the active study set, answer history, and question state. Preserve that pattern when changing quiz behavior.
- The study flow is centralized through `STUDY_ROUTES`, `STUDY_MODE_NAMES`, and the `_record_answer` logic in [app.py](app.py). Update all relevant mode mappings if adding or renaming a study mode.
- This project stores data in a local SQLite file (`vocab.db`), which is created on startup by `init_db()` in [database.py](database.py).

## Local workflow

- Create a Python virtual environment in the project directory: `python3 -m venv .venv`
- Activate it: `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows)
- Install dependencies: `pip install -r requirements.txt`
- Start the app: `python app.py`
- App entry point: the Flask app runs on `0.0.0.0:20250` in debug mode.
- The project does not appear to have a formal automated test suite; validate changes by running the app and exercising the affected route or behavior.

## Data migration notes

- Legacy CSV import is handled by [migrate_csv.py](migrate_csv.py). Do not treat it as a general database-management tool.
- If you need to import or reset data, make sure you understand the existing SQLite schema before modifying it.

## Preferred agent behavior

- Before making a change, check the relevant route and data-access function together, because the app’s state is split between Flask session state and SQLite records.
- When editing templates, keep the same session-driven flow and variable names used by the route functions.
- When adding a new feature, update both the view logic and the database/query layer together rather than changing only one side.
