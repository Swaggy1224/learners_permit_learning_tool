import random
import csv
from playwright.sync_api import sync_playwright

# Load existing data from CSV to a dictionary for quick access
def load_known_answers(csv_file):
    known_answers = {}
    try:
        with open(csv_file, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                question = row['Question']
                known_answers[question] = {
                    'correct': None,
                    'incorrect': [],
                    'options': [row[f'Option {i+1}'] for i in range(len(row) - 1)]
                }
                for option in known_answers[question]['options']:
                    if "(Correct)" in option:
                        known_answers[question]['correct'] = option.replace(" (Correct)", "")
                    elif "(Incorrect)" in option:
                        known_answers[question]['incorrect'].append(option.replace(" (Incorrect)", ""))
    except FileNotFoundError:
        pass  # If the file doesn't exist, we have no known answers
    return known_answers

def update_csv(csv_file, question_text, chosen_answer_text, result):
    # Read the existing data into memory
    with open(csv_file, mode='r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        rows = list(reader)  # Convert iterator to a list to reuse it

    # Update the correct or incorrect answer in the data
    updated = False
    for row in rows:
        if row['Question'] == question_text:
            for i in range(1, len(row)):
                option_key = f'Option {i}'
                # Update only if the option is not already marked as correct or incorrect
                if row[option_key].strip() == chosen_answer_text and "(Correct)" not in row[option_key] and "(Incorrect)" not in row[option_key]:
                    row[option_key] += f" {result}"
                    updated = True
                    break

    # Write the updated data back to the CSV
    if updated:
        with open(csv_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def scrape_question(page, known_answers):
    question_element = page.wait_for_selector("h3.font-weight-normal span")
    question_text = question_element.text_content().strip()

    option_divs = page.query_selector_all("div.option")
    options_text = [div.text_content().strip() for div in option_divs]

    # If the question has been answered before
    if question_text in known_answers:
        # If the correct answer is known, click it
        if known_answers[question_text]['correct']:
            correct_answer = known_answers[question_text]['correct']
            for div in option_divs:
                if div.text_content().strip() == correct_answer:
                    div.click()
                    return question_text, options_text, True  # Known correct answer was used
        else:
            # Choose an answer that is not marked as incorrect
            incorrect_answers = known_answers[question_text]['incorrect']
            possible_answers = [opt for opt in options_text if opt not in incorrect_answers]
            if possible_answers:
                chosen_answer_text = random.choice(possible_answers)
            else:
                chosen_answer_text = options_text[0]  # All options are incorrect, choose the first one
            # Click the chosen answer
            for div in option_divs:
                if div.text_content().strip() == chosen_answer_text:
                    div.click()
                    break
            # Wait for the result to appear
            page.wait_for_timeout(1000)
            # Check the result and update the CSV accordingly
            result = "(Correct)" if page.is_visible("div.h3.text-success") else "(Incorrect)"
            update_csv('quiz_results.csv', question_text, chosen_answer_text, result)
            return question_text, options_text, False  # New answer was attempted
    else:
        # If the question is not a duplicate, choose a random answer
        random_div = random.choice(option_divs)
        chosen_answer_text = random_div.text_content().strip()
        random_div.click()
        # Wait for the result to appear
        page.wait_for_timeout(1000)
        # Check the result
        result = "(Correct)" if page.is_visible("div.h3.text-success") else "(Incorrect)"
        # Append the result to the chosen answer
        chosen_answer_index = options_text.index(chosen_answer_text)
        options_text[chosen_answer_index] += f" {result}"
        return question_text, options_text, False  # No known correct answer was used

    # If none of the above conditions are met, return a default value
    return question_text, options_text, False



def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://mvarookie.mva.maryland.gov/?id=MVA-English-tutorial-not-timed")

    known_answers = load_known_answers('quiz_results.csv')
    questions_answered = 0

    while True:
        question_text, options_text, used_known_answer = scrape_question(page, known_answers)

        # If we didn't use a known correct answer, update the CSV
        if not used_known_answer:
            # Prepare the data for the CSV
            data = {
                'Question': question_text,
                **{f'Option {i+1}': option for i, option in enumerate(options_text)}
            }

            # Write to CSV in append mode
            with open('quiz_results.csv', mode='a', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=data.keys())
                if file.tell() == 0:  # Write header only if file is empty
                    writer.writeheader()
                writer.writerow(data)

        # Wait 2 seconds
        page.wait_for_timeout(2000)

        # Press the 'cancel' button if it exists to move to the next question
        if page.is_visible("#cancel"):
            cancel_button = page.wait_for_selector("#cancel")
            cancel_button.click()

        # Wait for the next question to load if necessary
        page.wait_for_timeout(2000)

        questions_answered += 1
        if questions_answered >= 25:
            # Restart the quiz by refreshing the page or navigating to the quiz start URL
            page.reload()
            # Wait for the page to reload and for the necessary elements to be available again
            page.wait_for_selector("h3.font-weight-normal span")
            # Reset the counter
            questions_answered = 0

    # Close the browser
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
