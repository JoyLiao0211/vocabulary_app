import csv
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session
import random

# -- Local CSV "database" as list of dicts ------------------------------
DATA_FILE = 'data.csv'

# Data loaded as list of dicts
# Each dict: {"ID": int, "Term": str, "Definitions": [str], "Scores": [float], "AccessTime": [date_str]}
data = []


def load_data():
    global data
    data = []
    with open(DATA_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            defs = row['NewDefinition'].splitlines()
            scores = [float(s) for s in row['Scores'].splitlines()]
            times  = row['AccessTime'].splitlines()
            data.append({
                'ID': int(row['ID']),
                'Term': row['Term'],
                'Definitions': defs,
                'Scores': scores,
                'AccessTime': times
            })


def save_data():
    # write back to CSV in same multi-line format
    with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['ID','Term','NewDefinition','Scores','AccessTime']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in data:
            writer.writerow({
                'ID': item['ID'],
                'Term': item['Term'],
                'NewDefinition': '\n'.join(item['Definitions']),
                'Scores': '\n'.join(str(s) for s in item['Scores']),
                'AccessTime': '\n'.join(item['AccessTime'])
            })

# initialize on startup
load_data()

# helpers

def vocab_count():
    return len(data)

def avg(lst):
    return sum(lst) / len(lst) if lst else 0

def get_least_familiar_questions(start, end, number):
    # compute average scores per ID
    subset = [item for item in data if start <= item['ID'] < end]
    subset.sort(key=lambda x: avg(x['Scores']))
    return [item['ID'] for item in subset[:number]]


def get_least_familiar_and_last_accessed_questions(start, end, number):
    today = date.today().isoformat()
    def metric(item):
        # avg score minus 0.05 * avg days since
        scores = item['Scores']
        dates = [date.fromisoformat(d) for d in item['AccessTime']]
        avg_score = sum(scores)/len(scores)
        days = [(date.today() - d).days for d in dates]
        avg_days = sum(days)/len(days)
        return avg_score - 0.05 * avg_days
    subset = [item for item in data if start <= item['ID'] < end]
    subset.sort(key=metric)
    return [item['ID'] for item in subset[:number]]


def update_words(word_ids, correct_list, weight):
    today = date.today().isoformat()
    for wid, is_corr in zip(word_ids, correct_list):
        item = next((i for i in data if i['ID']==wid), None)
        if not item:
            continue
        # update each definition entry
        item['AccessTime'] = [today] * len(item['AccessTime'])
        if weight > 0:
            item['Scores'] = [s*(1-weight) + (1 if is_corr else 0)*weight for s in item['Scores']]
    save_data()

# -- Flask App -----------------------------------------------------------
app = Flask(__name__)
app.secret_key = 'replace_with_a_random_string'
app.permanent_session_lifetime = timedelta(days=30)

# Study mode weights
db_weights = {1: 0, 2: 0.2, 3: 0.2}
vocab_num = vocab_count()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        session.permanent = True
        session['start'] = int(request.form['start'])
        session['end']   = min(int(request.form['end']), vocab_num)
        if session['end'] > session.get('progress', 0):
            session['progress'] = session['end']
        session['number'] = int(request.form['number'])
        session['order']  = int(request.form['order'])
        session['type']   = int(request.form['type'])
        return redirect(url_for('redirect_to_question'))
    progress = session.get('progress', 0)
    return render_template('index.html', progress=progress)

@app.route('/redirect_to_question')
def redirect_to_question():
    _prepare_session_questions()
    t = session['type']
    if t == 1:
        return redirect(url_for('study_flashcard'))
    if t == 2:
        return redirect(url_for('study_multiple_choice'))
    if t == 3:
        return redirect(url_for('study_spelling'))
    return "Invalid type", 404

@app.route('/study/flashcard')
def study_flashcard():
    _prepare_current_question()
    qid = session.get('current_question')
    if qid is None:
        session['results'] = [True]*len(session['questions'])
        return redirect(url_for('results'))
    item = next(i for i in data if i['ID']==qid)
    # show first definition
    return render_template('flashcard.html', term=item['Term'], definition=" / ".join(item['Definitions']))

@app.route('/study/multiple_choice', methods=['GET', 'POST'])
def study_multiple_choice():
    if request.method == 'POST':
        qid = session['current_question']
        user_idx = int(request.form['answer'])
        choices = session['current_choices']
        correct = session['correct_answer']
        is_corr = (choices[user_idx] == correct)
        session.setdefault('results', []).append(is_corr)
        feedback = "Correct!" if is_corr else f"Wrong! The correct answer was: {correct}"
        return render_template('multiple_choice.html', term=session['current_term'],
                               choices=choices, feedback=feedback)
    _prepare_current_question()
    qid = session.get('current_question')
    if qid is None:
        return redirect(url_for('results'))
    item = next(i for i in data if i['ID']==qid)
    # take Term as correct, show Definitions
    term = item['Term']
    definition = item['Definitions'][0]
    others = [i['ID'] for i in data if i['ID']!=qid]
    distract = random.sample(others, 3)
    ids = distract + [qid]
    random.shuffle(ids)
    choices = [next(i['Term'] for i in data if i['ID']==x) for x in ids]
    session['current_choices'] = choices
    session['correct_answer']   = term
    session['current_term']     = definition
    return render_template('multiple_choice.html', term=definition, choices=choices)

@app.route('/study/spelling', methods=['GET', 'POST'])
def study_spelling():
    if request.method == 'POST':
        answer = request.form['answer'].strip().lower()
        correct = session['correct_answer'].lower()
        is_corr = (answer == correct)
        session.setdefault('results', []).append(is_corr)
        feedback = "Correct!" if is_corr else f"Wrong! The correct answer was: {session['correct_answer']}"
        return render_template('spelling.html', feedback=feedback)
    _prepare_current_question()
    qid = session.get('current_question')
    if qid is None:
        return redirect(url_for('results'))
    item = next(i for i in data if i['ID']==qid)
    session['correct_answer'] = item['Term']
    return render_template('spelling.html', definition=item['Definitions'][0])

@app.route('/results')
def results():
    update_words(session.get('questions', []), session.get('results', []), db_weights[session['type']])
    correct = sum(session.get('results', []))
    incorrect = len(session.get('results', [])) - correct
    for k in ['questions','results','current_number','current_question']:
        session.pop(k, None)
    return render_template('results.html', correct_count=correct, incorrect_count=incorrect)

@app.route('/retry_wrongs')
def retry_wrongs():
    wrongs = session.get('wrong_questions', [])
    if not wrongs:
        return redirect(url_for('index'))
    session['questions'] = wrongs
    session.pop('wrong_questions', None)
    session['current_number'] = 0
    return redirect(url_for({1:'study_flashcard',2:'study_multiple_choice',3:'study_spelling'}[session['type']]))

# -- Session helpers -----------------------------------------------------
def _prepare_session_questions():
    session.pop('wrong_questions', None)
    start  = session['start']
    end    = session['end']
    num    = min(session['number'], end-start)
    order  = session['order']
    if order == 1:
        qs = list(range(start, start+num))
    elif order == 2:
        qs = get_least_familiar_questions(start, end, num)
    else:
        qs = get_least_familiar_and_last_accessed_questions(start, end, num)
    session['questions']       = qs
    session['current_number']  = 0
    session['results']         = []
    session['current_question'] = None


def _prepare_current_question():
    idx = session.get('current_number', 0)
    qs  = session.get('questions', [])
    if idx < len(qs):
        session['current_question'] = qs[idx]
        session['current_number'] = idx+1
    else:
        session['current_question'] = None

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=20250)
