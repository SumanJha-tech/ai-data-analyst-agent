import json

import demo_mode
from demo_mode import find_demo_answer, suggest_questions, load_demo_answers

EXAMPLES = [
    "Which product category had the highest total revenue?",
    "What is the average delivery time in days?",
    "Which state has the most delayed deliveries?",
    "What is the most common payment type?",
    "How many orders have a review score of 1 or 2?",
    "What are the top 5 product categories by total revenue?",
]


def test_every_try_one_of_these_question_matches_exactly():
    for q in EXAMPLES:
        assert find_demo_answer(q)["question"] == q


def test_match_ignores_case_and_punctuation():
    assert find_demo_answer("which STATE has the most delayed deliveries")["question"] == EXAMPLES[2]


def test_fuzzy_match():
    assert find_demo_answer("average delivery time")["question"] == EXAMPLES[1]
    assert find_demo_answer("top 5 categories by revenue")["question"] == EXAMPLES[5]
    assert find_demo_answer("how many orders were late?")["question"] == "How many orders were delivered late?"


def test_opposite_meaning_does_not_match():
    assert find_demo_answer("What are the bottom 5 product categories by total revenue?") is None
    assert find_demo_answer("What are the top 10 product categories by total revenue?") is None


def test_unrelated_or_empty_question_returns_none():
    assert find_demo_answer("What is the weather in Sao Paulo?") is None
    assert find_demo_answer("") is None
    assert find_demo_answer("   ") is None


def test_suggestions_are_limited_and_exclude_current():
    suggestions = suggest_questions(4, exclude=EXAMPLES[0])
    assert len(suggestions) == 4
    assert EXAMPLES[0] not in suggestions
    assert all(find_demo_answer(s) for s in suggestions)


def test_demo_answers_file_is_well_formed():
    answers = load_demo_answers()
    assert 8 <= len(answers) <= 15
    for a in answers:
        assert set(a) == {"question", "sql", "result", "chart_type", "insight"}
        assert a["result"] and a["chart_type"] in {"none", "pie", "bar", "line"}
        assert a["sql"].strip().upper().startswith("SELECT")


def test_demo_answers_are_real_not_stale():
    """Rebuilding from the CSVs must reproduce the committed file exactly."""
    from scripts.build_demo_answers import build
    assert build() == json.loads(demo_mode.DEMO_FILE.read_text(encoding="utf-8"))
