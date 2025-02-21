from flask import Flask, render_template, request, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
import pandas as pd
import random
from google_sheets_functions import *
import json
from datetime import timedelta

app = Flask(__name__)
app.secret_key = '1jhbkc132i4yo'  # just a random string
app.permanent_session_lifetime = timedelta(days=30)

oauth = OAuth(app)
with open('oath_client_id.json', 'r') as file:
    google_credentials = json.load(file)['web']  # 'web' key contains OAuth 2.0 details

google = oauth.register(
    name='google',
    client_id=google_credentials['client_id'],
    client_secret=google_credentials['client_secret'],
    access_token_url=google_credentials['token_uri'],
    access_token_params=None,
    authorize_url=google_credentials['auth_uri'],
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    client_kwargs={'scope': 'email'},
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)

contents = pd.read_csv('static/contents_original.csv')

weights = dict({
    1:0, # flashcard
    2:0.2, # multiple choice
    3:0.2 # spelling
})


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        session['start'] = int(request.form['start'])
        session['end'] = int(request.form['end'])
        session['end'] = min(session['end'], vocab_num)
        if int(session['end']) > int(session['progress']):
            session['progress'] = session['end']
            update_progress(session['user_id'], session['progress'])
        session['number'] = int(request.form['number'])
        session['order'] = int(request.form['order'])
        session['type'] = int(request.form['type'])
        app.logger.debug(f"Session data: {session}")
        return redirect(url_for('redirect_to_question'))
    if 'user_email' not in session:
        return redirect(url_for('login'))
    if 'user_id' not in session:
        session['user_id'] = find_user_id_by_email(session['user_email'])
    if 'progress' not in session:
        session['progress'] = int(get_progress_by_user_id(session['user_id']))
    stats = get_stats_by_user_id(session['user_id'])
    return render_template(
        'index.html',
        progress=session['progress'],
        email=session['user_email'],
        stats=stats
    )

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()
    app.logger.debug(user_info)
    user_email = user_info['email']
    user_login(user_email)
    app.logger.debug(f"User {user_email} logged in")
    return redirect(url_for('index'))

def user_login(user_email):
    session.permanent = True
    session['user_email'] = user_email
    user_id = find_user_id_by_email(user_email)
    if user_id == None:
        user_id = create_new_user(user_email)
    session['user_id'] = user_id
    session['progress'] = get_progress_by_user_id(user_id)
def user_logout():
    session.permanent = False
    session.pop('user_email', None)
    session.pop('user_id',None)
    session.pop('progress', None)

@app.route('/logout')
def logout():
    user_logout()
    return redirect(url_for('index'))

@app.route('/redirect_to_question')
def redirect_to_question():
    prepare_session_questions()
    if session['type'] == 1:
        return redirect(url_for('study_flashcard'))
    elif session['type'] == 2:
        return redirect(url_for('study_multiple_choice'))
    elif session['type'] == 3:
        return redirect(url_for('study_spelling'))
    else:
        return "Invalid question type", 404

@app.route('/study/flashcard')
def study_flashcard():
    app.logger.debug("study_flashcard")
    prepare_current_question()
    question_id = session.get('current_question', None)
    if question_id is not None:
        app.logger.debug(f"line 102, Current question: {question_id}")
        question = contents.loc[question_id]
        return render_template(
            'flashcard.html',
            question_id=question_id,
            term=question['Term'],
            definition=question['Definition']
        )
    session['results'] = [True]*len(session['questions'])
    return redirect(url_for('results'))

@app.route('/study/multiple_choice', methods=['GET', 'POST'])
def study_multiple_choice():
    if request.method == 'POST':
        # Process the submitted answer
        question_id = session.get('current_question', None)
        user_answer_index = int(request.form.get('answer'))
        choices = session.get('current_choices', [])
        correct_answer = session.get('correct_answer')

        # Check if the selected answer is correct
        is_correct = choices[user_answer_index] == correct_answer
        session['results'].append(is_correct)
        # Update session counts
        if is_correct:
            session['correct_count'] = session.get('correct_count', 0) + 1
            return render_template(
                'multiple_choice.html',
                question_id=question_id,
                term=session['current_term'],
                choices=session['current_choices'],
                feedback="Correct!",
                is_correct=True,
                redirect=True
            )
        else:
            session['incorrect_count'] = session.get('incorrect_count', 0) + 1
            if 'wrong_questions' not in session:
                session['wrong_questions'] = []
            session['wrong_questions'].append(question_id)
            return render_template(
                'multiple_choice.html',
                question_id=question_id,
                term=session['current_term'],
                choices=session['current_choices'],
                feedback=f"Wrong! The correct answer was: {correct_answer}",
                is_correct=False,
                redirect=False
            )

    # Prepare the next question for GET request
    prepare_current_question()
    question_id = session.get('current_question', None)
    if question_id is not None:
        question = contents.loc[question_id]
        all_choices_id = random.sample(list(range(0, question_id))+list(range(question_id+1, vocab_num)), 3) + [question_id]
        random.shuffle(all_choices_id)
        all_choices = [contents.loc[choice, "Definition"] for choice in all_choices_id]
        session['current_choices'] = all_choices  # Store choices for answer validation
        session['correct_answer'] = question['Definition']
        session['current_term'] = question['Term']
        return render_template(
            'multiple_choice.html',
            question_id=question_id,
            term=question['Term'],
            choices=all_choices,
            redirect=False
        )
    # Redirect to results page if no more questions
    return redirect(url_for('results'))

@app.route('/study/spelling', methods=['GET', 'POST'])
def study_spelling():
    app.logger.debug("study_spelling")
    if request.method == 'POST':
        # Process the submitted answer
        question_id = session.get('current_question', None)
        user_answer = request.form.get('answer')
        correct_answer = session.get('correct_answer')

        # Check if the selected answer is correct
        is_correct = user_answer.lower() == correct_answer.lower()
        # update_a_word(session['user_id'], question_id, is_correct, 0.2)
        session['results'].append(is_correct)

        # Update session counts
        if is_correct:
            session['correct_count'] = session.get('correct_count', 0) + 1
        else:
            session['incorrect_count'] = session.get('incorrect_count', 0) + 1
            if 'wrong_questions' not in session:
                session['wrong_questions'] = []
            session['wrong_questions'].append(question_id)

        # Feedback and redirection
        feedback = "Correct!" if is_correct else f"Wrong! The correct answer was: {correct_answer}"
        return render_template('spelling.html', feedback=feedback, is_correct=is_correct, redirect=True)
    prepare_current_question()
    question_id = session.get('current_question', None)
    if question_id != None:
        question = contents.loc[question_id]
        session['correct_answer'] = question['Term']
        return render_template('spelling.html', definition=question['Definition'])
    return redirect(url_for('results'))

@app.route('/results', methods=['GET'])
def results():
    update_words(session['user_id'], session['questions'], session['results'], weights[session['type']])
    correct_count = session.get('correct_count', 0)
    incorrect_count = session.get('incorrect_count', 0)
    session['correct_count'] = 0
    session['incorrect_count'] = 0
    session['questions'] = []
    session['results'] = []
    app.logger.debug(f"wrong questions: {session.get('wrong_questions', [])}")
    if session['type'] == 1:
        return redirect(url_for('index'))
    return render_template('results.html', correct_count=correct_count, incorrect_count=incorrect_count)

@app.route('/retry_wrongs', methods=['GET'])
def retry_wrongs():
    
    if 'wrong_questions' in session and session['wrong_questions']:
        app.logger.debug(f"wrong questions: {session['wrong_questions']}")
        session['questions'] = session['wrong_questions']  # Repopulate the questions list
        session['wrong_questions'] = []  # Clear wrong questions to avoid duplication
        session['current_number'] = 0
        session['current_question'] = None  # Reset current question
        app.logger.debug("Retrying wrong questions")
        # Redirect based on the question type stored in session
        question_type = session.get('type', 1)
        if question_type == 1:
            return redirect(url_for('study_flashcard'))
        elif question_type == 2:
            return redirect(url_for('study_multiple_choice'))
        elif question_type == 3:
            return redirect(url_for('study_spelling'))
    else:
        # If no wrong questions, redirect to the results page
        return redirect(url_for('index'))

def prepare_session_questions():
    app.logger.debug("Preparing session questions")
    session.pop('wrong_questions', None)
    start = session.get('start', 0)
    end = session.get('end', vocab_num)
    number = session.get('number', 10)
    number = min(number, end-start)
    order = session.get('order', 1)
    if order == 1: # original order
        questions = list(range(start, start+number))
    elif order == 2: # sort by score, lowest first
        questions = get_least_familiar_questions(session['user_id'], start, end, number)
    elif order == 3: # sort by score and last time accessed
        questions = get_least_familiar_and_last_accessed_questions(session['user_id'], start, end, number)
    elif order == 4: # random order
        questions = random.sample(range(start, end), number)
    app.logger.debug(f"number of questions:{len(questions)}")
    session['questions'] = questions
    session['current_number'] = 0
    session['results'] = []
    session['current_question'] = None

def prepare_current_question():
    current_number = session.get('current_number', 0)
    questions = session.get('questions', [])
    if current_number < len(questions):
        current_question = questions[current_number]
        session['current_question'] = current_question
        current_number += 1
        session['current_number'] = current_number
    else:
        session['current_question'] = None

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=20250)
