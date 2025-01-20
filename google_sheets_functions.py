import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# Authenticate with Google Sheets
credentials = Credentials.from_service_account_file('data_credentials.json')
scoped_credentials = credentials.with_scopes(['https://www.googleapis.com/auth/spreadsheets'])
client = gspread.authorize(scoped_credentials)

# Open your Google Sheet
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1A_kjcQrtdwgwt-XVLMuMMQ9Rg1kUl5dPQa8ZynkP0hQ")  # Use .worksheet('SheetName') if needed

contents = sheet.worksheet('contents')
scores = sheet.worksheet('scores')
last_access_date = sheet.worksheet('last_access_date')
least_familiar = sheet.worksheet('least_familiar')
least_familiar_and_last_accessed = sheet.worksheet('least_familiar_and_last_accessed')
progresses = sheet.worksheet('progresses')
vocab_num = 1079

def get_column_name(index):
    """Convert a 1-based column index to a column name (e.g., 1 -> A, 27 -> AA)."""
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name

'''
get questions by least familiar method
'''
def get_least_familiar_questions(user_id:int, start:int, end:int, number:int)->list:
    column_name = get_column_name(user_id + 2)
    least_familiar.update(
        range_name = f"{column_name}2:{column_name}3",
        values = [[start], [end]],
        value_input_option='USER_ENTERED'
    )
    arr = least_familiar.get(f"{column_name}4:{column_name}{3+number}")
    return [int(row[0]) for row in arr]

'''
get questions by least familiar and last accessed
'''
def get_least_familiar_and_last_accessed_questions(user_id:int, start:int, end:int, number:int)->list:
    column_name = get_column_name(user_id + 2)
    least_familiar_and_last_accessed.update(
        range_name = f"{column_name}2:{column_name}3",
        values = [[start], [end]],
        value_input_option='USER_ENTERED'
    )
    arr = least_familiar_and_last_accessed.get(f"{column_name}4:{column_name}{3+number}")
    return [int(row[0]) for row in arr]


def update_words(user_id: int, word_ids: list[int], correct: list[bool], weight: float) -> None:
    """
    Update scores and last access dates in a batch for a specific user and multiple words.
    - user_id: User ID (integer).
    - word_ids: List of word IDs (integer).
    - correct: List of correctness (boolean) corresponding to word_ids.
    - weight: Weight of the new response.
    """
    # Get the column name for the user's data
    column_name = get_column_name(user_id + 2)

    # Step 1: Update last access dates
    last_access_updates = []
    for word_id in word_ids:
        cell_name = f"{column_name}{word_id + 2}"
        last_access_updates.append({
            'range': f"{cell_name}",
            'values': [[str(pd.Timestamp('today').date())]]
        })

    if last_access_updates:
        last_access_date.batch_update(
            value_input_option = 'USER_ENTERED',
            data = last_access_updates
        )

    # If weight is 0, no need to update scores
    if weight == 0:
        return

    # Step 2: Batch retrieve original scores
    score_ranges = [f"{column_name}{word_id + 2}" for word_id in word_ids]
    score_data = scores.batch_get(score_ranges)

    # Step 3: Prepare updates for scores
    score_updates = []
    for word_id, is_correct, org_score_data in zip(word_ids, correct, score_data):
        cell_name = f"{column_name}{word_id + 2}"
        # Fetch original score
        if not org_score_data:
            continue

        org_score = float(org_score_data[0][0])
        # Calculate the new score
        new_score = org_score * (1 - weight) + int(is_correct) * weight
        # Add the update to the batch
        score_updates.append({
            'range': f"{cell_name}",
            'values': [[new_score]]
        })

    # Step 4: Perform batch updates for scores
    if score_updates:
        scores.batch_update(
            value_input_option = 'USER_ENTERED',
            data = score_updates
        )


'''
find user id by email
'''
def find_user_id_by_email(email): # 0-indexed
    cell = progresses.find(email)
    if cell and cell.col == 1:
        return cell.row - 2
    return None

def get_progress_by_user_id(user_id: int):
    cell_range = f"B{user_id + 2}"
    progress_data = progresses.get(cell_range)
    return int(progress_data[0][0])
    return (int(progress_data[0][0]), [int(progress_data[0][1]), int(progress_data[0][2]), int(progress_data[0][3])])

def get_stats_by_user_id(user_id: int):
    cell_range = f"C{user_id + 2}:E{user_id + 2}"
    stats_data = progresses.get(cell_range)
    return [int(stats_data[0][0]), int(stats_data[0][1]), int(stats_data[0][2])]

def update_progress(user_id: int, new_progress: int):
    cell_name = f"B{user_id + 2}"
    progresses.update(
        range_name = cell_name,
        values = [[new_progress]],
        value_input_option = 'USER_ENTERED'
    )

'''
create a new user, return user id
'''
def create_new_user(email):
    progresses.append_row([email, "0"]) #email and progress
    user_id = find_user_id_by_email(email)

    column_name = get_column_name(2 + user_id) # starting from B
    scores.update(
        range_name=f"{column_name}:{column_name}",
        values=[[email]] + [["0"]]*vocab_num,
        value_input_option='USER_ENTERED'
    )
    last_access_date.update(
        values=[[email]] + [["1677-09-21"]]*vocab_num,
        range_name=f"{column_name}:{column_name}",
        value_input_option='USER_ENTERED'
    )
    least_familiar_formula = f"=INDEX(SORT(FILTER({{scores!$A$2:$A, scores!{column_name}$2:{column_name}}},scores!$A$2:$A >={column_name}2,scores!$A$2:$A<{column_name}3), 2,TRUE), 0, 1)"
    least_familiar.update(
        range_name=f"{column_name}:{column_name}",
        values=[[email], ["0"], ["15"], [least_familiar_formula]],
        value_input_option='USER_ENTERED'
    )
    # formula: =INDEX(SORT(FILTER({scores!$A$2:$A, scores!C$2:C - 0.05*(TODAY() - last_access_date!C$2:C)},scores!$A$2:$A >=C$2,scores!$A$2:$A<C$3), 2,TRUE), 0, 1)
    least_familiar_and_last_accessed_formula = f"=INDEX(SORT(FILTER({{scores!$A$2:$A, scores!{column_name}$2:{column_name} - 0.05*(TODAY() - last_access_date!{column_name}$2:{column_name})}},scores!$A$2:$A >={column_name}$2,scores!$A$2:$A<{column_name}$3), 2,TRUE), 0, 1)"
    least_familiar_and_last_accessed.update(
        range_name=f"{column_name}:{column_name}",
        values=[[email], ["0"], ["15"], [least_familiar_and_last_accessed_formula]],
        value_input_option='USER_ENTERED'
    )
    return user_id

# print([["hahaha"]] + [["0"]]*vocab_num)


# q = get_least_familiar_and_last_accessed_questions(0, 5, 100, 15)
# print(q)