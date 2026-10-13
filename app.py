"""Flask application for vocabulary study."""

import random
from datetime import timedelta

from flask import Flask, redirect, render_template, request, session, url_for

from database import (
    get_entry,
    get_entry_count,
    get_entries_in_range,
    get_least_familiar_and_last_accessed_questions,
    get_least_familiar_questions,
    get_random_distractor_terms,
    init_db,
    record_attempt,
)

app = Flask(__name__)
app.secret_key = "replace_with_a_random_string"
app.permanent_session_lifetime = timedelta(days=30)

# Study modes: 1 = flashcard, 2 = multiple choice, 3 = spelling.
DB_WEIGHTS = {
    1: 0.0,
    2: 0.2,
    3: 0.2,
}

STUDY_ROUTES = {
    1: "study_flashcard",
    2: "study_multiple_choice",
    3: "study_spelling",
}

STUDY_MODE_NAMES = {
    1: "flashcard",
    2: "multiple_choice",
    3: "spelling",
}

init_db()


@app.route("/", methods=["GET", "POST"])
def index():
    """Display study settings and initialize a new study session."""
    if request.method == "POST":
        try:
            start = int(request.form["start"])
            end = int(request.form["end"])
            number = int(request.form["number"])
            order = int(request.form["order"])
            study_type = int(request.form["type"])
        except (KeyError, ValueError):
            return "Invalid study settings", 400

        vocab_num = get_entry_count()

        start = max(0, min(start, vocab_num))
        end = max(0, min(end, vocab_num))

        if start >= end:
            return "The end must be greater than the start", 400

        if number <= 0:
            return "The number of questions must be positive", 400

        if order not in (1, 2, 3):
            return "Invalid question order", 400

        if study_type not in STUDY_ROUTES:
            return "Invalid study type", 400

        session.permanent = True
        session["start"] = start
        session["end"] = end
        session["number"] = number
        session["order"] = order
        session["type"] = study_type
        session["progress"] = max(
            session.get("progress", 0),
            end,
        )

        return redirect(url_for("redirect_to_question"))

    return render_template(
        "index.html",
        progress=session.get("progress", 0),
    )


@app.route("/redirect_to_question")
def redirect_to_question():
    """Select questions and redirect to the chosen study mode."""
    if "type" not in session:
        return redirect(url_for("index"))

    _prepare_session_questions()

    return redirect(url_for(STUDY_ROUTES[session["type"]]))


def _prepare_session_questions() -> None:
    """Select a new set of questions using the configured ordering strategy."""
    start = session["start"]
    end = session["end"]
    number = session["number"]
    order = session["order"]

    available_ids = get_entries_in_range(start, end)
    number = min(number, len(available_ids))

    if order == 1:
        questions = available_ids[:number]
    elif order == 2:
        questions = get_least_familiar_questions(
            start,
            end,
            number,
        )
    else:
        questions = get_least_familiar_and_last_accessed_questions(
            start,
            end,
            number,
        )

    session["questions"] = questions
    session["current_number"] = 0
    session["results"] = []
    session["wrong_questions"] = []
    session.pop("current_question", None)
    session.pop("current_choices", None)
    session.pop("correct_answer", None)
    session.pop("current_term", None)
    session.pop("last_feedback", None)


def _prepare_current_question() -> int | None:
    """Return the current question ID without advancing the question index."""
    questions = session.get("questions", [])
    index = session.get("current_number", 0)

    if index >= len(questions):
        session.pop("current_question", None)
        return None

    question_id = questions[index]
    session["current_question"] = question_id

    return question_id


def _record_answer(
    entry_id: int,
    is_correct: bool,
    mode: str,
) -> None:
    """Record one answer, update progress, and advance the session."""
    record_attempt(
        entry_id=entry_id,
        is_correct=is_correct,
        mode=mode,
        weight=DB_WEIGHTS[session["type"]],
    )

    session.setdefault("results", []).append(is_correct)

    if not is_correct:
        wrong_questions = session.setdefault("wrong_questions", [])

        if entry_id not in wrong_questions:
            wrong_questions.append(entry_id)

    session["last_question_id"] = entry_id
    session["last_question_choices"] = session.get("current_choices")
    session["last_question_correct_answer"] = session.get("correct_answer")
    session["last_question_term"] = session.get("current_term")

    session["current_number"] = session.get("current_number", 0) + 1
    session.pop("current_question", None)
    session.pop("current_choices", None)
    session.pop("correct_answer", None)
    session.pop("current_term", None)

    session["last_feedback"] = "Correct!" if is_correct else "Incorrect."


def _get_current_entry():
    """Return the current vocabulary entry, or None when the study is complete."""
    question_id = _prepare_current_question()

    if question_id is None:
        return None

    entry = get_entry(question_id)

    if entry is None:
        raise RuntimeError(f"Vocabulary entry {question_id} no longer exists.")

    return entry


@app.route("/study/flashcard", methods=["GET", "POST"])
def study_flashcard():
    """Display a flashcard and record the learner's self-assessment."""
    if request.method == "POST":
        question_id = session.get("current_question")

        if question_id is None:
            return redirect(url_for("study_flashcard"))

        correct_value = request.form.get("correct", "1").casefold()
        is_correct = correct_value in {"1", "true", "yes", "correct"}

        _record_answer(
            question_id,
            is_correct,
            STUDY_MODE_NAMES[1],
        )

        return redirect(url_for("study_flashcard"))

    entry = _get_current_entry()

    if entry is None:
        return redirect(url_for("results"))

    feedback = session.pop("last_feedback", None)

    return render_template(
        "flashcard.html",
        question_id=entry.id,
        term=entry.term,
        definition=entry.definition,
        feedback=feedback,
    )


@app.route("/study/multiple_choice", methods=["GET", "POST"])
def study_multiple_choice():
    """Present a definition and ask the learner to identify its term."""
    if request.method == "POST":
        question_id = session.get("current_question")
        choices = session.get("current_choices")
        correct_answer = session.get("correct_answer")

        if question_id is None or choices is None or correct_answer is None:
            return redirect(url_for("study_multiple_choice"))

        try:
            user_index = int(request.form["answer"])
        except (KeyError, ValueError):
            return "Invalid answer", 400

        if not 0 <= user_index < len(choices):
            return "Answer index out of range", 400

        is_correct = choices[user_index] == correct_answer

        _record_answer(
            question_id,
            is_correct,
            STUDY_MODE_NAMES[2],
        )

        return redirect(url_for("study_multiple_choice"))

    feedback = session.pop("last_feedback", None)
    previous_question_id = session.pop("last_question_id", None)
    previous_choices = session.pop("last_question_choices", None)
    previous_correct_answer = session.pop("last_question_correct_answer", None)
    previous_term = session.pop("last_question_term", None)

    if feedback is not None and previous_question_id is not None:
        previous_entry = get_entry(previous_question_id)

        if previous_entry is not None:
            return render_template(
                "multiple_choice.html",
                question_id=previous_entry.id,
                term=previous_term or previous_entry.definition,
                choices=previous_choices or [previous_entry.term],
                feedback=feedback,
                is_correct=feedback == "Correct!",
                correct_answer=previous_correct_answer or previous_entry.term,
            )

    entry = _get_current_entry()

    if entry is None:
        return redirect(url_for("results"))

    distractors = get_random_distractor_terms(entry.term, 3)
    choices = distractors + [entry.term]
    random.shuffle(choices)

    session["current_choices"] = choices
    session["correct_answer"] = entry.term
    session["current_term"] = entry.definition

    is_correct = feedback == "Correct!" if feedback is not None else False

    return render_template(
        "multiple_choice.html",
        question_id=entry.id,
        term=entry.definition,
        choices=choices,
        feedback=feedback,
        is_correct=is_correct,
        correct_answer=entry.term,
    )


@app.route("/study/spelling", methods=["GET", "POST"])
def study_spelling():
    """Ask the learner to spell the term matching a definition."""
    if request.method == "POST":
        question_id = session.get("current_question")
        correct_answer = session.get("correct_answer")

        if question_id is None or correct_answer is None:
            return redirect(url_for("study_spelling"))

        answer = request.form.get("answer", "").strip().casefold()
        is_correct = answer == correct_answer.casefold()

        _record_answer(
            question_id,
            is_correct,
            STUDY_MODE_NAMES[3],
        )

        return redirect(url_for("study_spelling"))

    feedback = session.pop("last_feedback", None)
    previous_question_id = session.pop("last_question_id", None)
    previous_correct_answer = session.pop("last_question_correct_answer", None)
    previous_term = session.pop("last_question_term", None)

    if feedback is not None and previous_question_id is not None:
        previous_entry = get_entry(previous_question_id)

        if previous_entry is not None:
            return render_template(
                "spelling.html",
                definition=previous_term or previous_entry.definition,
                feedback=feedback,
                redirect=True,
                is_correct=feedback == "Correct!",
            )

    entry = _get_current_entry()

    if entry is None:
        return redirect(url_for("results"))

    session["correct_answer"] = entry.term

    is_correct = feedback == "Correct!" if feedback is not None else False

    return render_template(
        "spelling.html",
        definition=entry.definition,
        feedback=feedback,
        redirect=feedback is not None,
        is_correct=is_correct,
    )


@app.route("/results")
def results():
    """Display the results of the current study session."""
    results_list = session.get("results", [])

    correct_count = sum(results_list)
    incorrect_count = len(results_list) - correct_count

    # Preserve wrong_questions so the learner can retry incorrect answers.
    for key in (
        "questions",
        "results",
        "current_number",
        "current_question",
        "current_choices",
        "correct_answer",
        "current_term",
        "last_feedback",
    ):
        session.pop(key, None)

    return render_template(
        "results.html",
        correct_count=correct_count,
        incorrect_count=incorrect_count,
    )


@app.route("/retry_wrongs")
def retry_wrongs():
    """Start a new session containing only previously incorrect entries."""
    wrongs = session.get("wrong_questions", [])

    if not wrongs:
        return redirect(url_for("index"))

    study_type = session.get("type")

    if study_type not in STUDY_ROUTES:
        return redirect(url_for("index"))

    session["questions"] = wrongs.copy()
    session["wrong_questions"] = []
    session["results"] = []
    session["current_number"] = 0

    for key in (
        "current_question",
        "current_choices",
        "correct_answer",
        "current_term",
        "last_feedback",
    ):
        session.pop(key, None)

    return redirect(url_for(STUDY_ROUTES[study_type]))


if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=20250,
    )
