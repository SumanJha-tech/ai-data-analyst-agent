"""Demo mode: real, pre-computed answers (data/demo_answers.json) served when
Gemini is unavailable. Built by scripts/build_demo_answers.py from DuckDB.
"""
import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import pandas as pd

DEMO_FILE = Path(__file__).resolve().parent / "data" / "demo_answers.json"
DEMO_BADGE = "Demo answer (live AI unavailable)"

FUZZY_CUTOFF = 0.65

STOPWORDS = {
    "what", "which", "who", "how", "is", "are", "was", "were", "the", "a", "an", "of", "in", "on",
    "for", "to", "from", "by", "all", "there", "do", "does", "did", "have", "has", "had", "many",
    "much", "me", "show", "tell", "give", "please", "our", "we", "i", "and", "with", "per",
}

# Words that flip the meaning of a question. Two questions only match if they
# agree on all of these, so "bottom 5 ..." can never be answered by "top 5 ...".
_HIGH = {"top", "highest", "most", "max", "maximum", "best", "largest", "biggest", "greatest"}
_LOW = {"bottom", "lowest", "least", "min", "minimum", "worst", "smallest", "fewest"}
_MEANING_WORDS = {"fastest", "slowest", "average", "state", "city", "seller", "category",
                  "customer", "payment", "review", "freight"}


@lru_cache(maxsize=1)
def load_demo_answers():
    try:
        return json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _stem(word):
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _tokens(question):
    words = re.sub(r"[^a-z0-9]+", " ", question.lower()).split()
    return [_stem(w) for w in words]


def _canonical(tokens):
    high = {_stem(w) for w in _HIGH}
    low = {_stem(w) for w in _LOW}
    return ["HI" if t in high else "LO" if t in low else t for t in tokens]


def _meaning_signature(tokens):
    meaning = {_stem(w) for w in _MEANING_WORDS} | {"HI", "LO"}
    return {t for t in tokens if t in meaning or t.isdigit()}


def _content_tokens(tokens):
    stop = {_stem(w) for w in STOPWORDS}
    return {t for t in tokens if t not in stop}


def _score(a_tokens, b_tokens):
    ratio = SequenceMatcher(None, " ".join(a_tokens), " ".join(b_tokens)).ratio()
    a, b = _content_tokens(a_tokens), _content_tokens(b_tokens)
    jaccard = len(a & b) / len(a | b) if a | b else 0.0
    return max(ratio, jaccard)


def find_demo_answer(question, cutoff=FUZZY_CUTOFF):
    """Best saved answer for `question` (exact or fuzzy), or None."""
    if not question or not question.strip():
        return None

    q_tokens = _canonical(_tokens(question))
    q_signature = _meaning_signature(q_tokens)

    best, best_score = None, 0.0
    for entry in load_demo_answers():
        d_tokens = _canonical(_tokens(entry["question"]))
        if q_tokens == d_tokens:
            return entry
        if _meaning_signature(d_tokens) != q_signature:
            continue
        score = _score(q_tokens, d_tokens)
        if score > best_score:
            best, best_score = entry, score

    return best if best_score >= cutoff else None


def suggest_questions(n=4, exclude=None):
    """First n demo questions (the 'Try one of these' set), skipping `exclude`."""
    questions = [e["question"] for e in load_demo_answers()]
    if exclude:
        questions = [q for q in questions if q != exclude]
    return questions[:n]


def demo_result_frame(entry):
    return pd.DataFrame(entry["result"])


def demo_chart(df, chart_type):
    import plotly.express as px

    if chart_type == "none" or df.shape[1] != 2:
        return None
    label_col, value_col = df.columns[0], df.columns[1]
    if chart_type == "pie":
        return px.pie(df, names=label_col, values=value_col, hole=0.45)
    if chart_type == "line":
        return px.line(df, x=label_col, y=value_col, markers=True)
    if chart_type == "bar":
        return px.bar(df, x=label_col, y=value_col)
    return None
