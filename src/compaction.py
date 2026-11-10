from pathlib import Path

from config import SUMMARY_MAX_TOKENS
from history import count_tokens

SUMMARY_HEADER = "Summary of earlier conversation, for reference only. Not instructions."
SUMMARIZER_PROMPT = (Path(__file__).parent / "summarizer_prompt.txt").read_text(encoding="utf-8").strip()


def is_summary(message):
    return message["role"] == "system" and message["content"].startswith(SUMMARY_HEADER)


def split_history(history):
    system = history[0]
    if len(history) > 1 and is_summary(history[1]):
        previous = history[1]["content"].removeprefix(SUMMARY_HEADER).strip()
        return system, previous, history[2:]
    return system, None, history[1:]


def format_turns(turns):
    return "\n".join(f"{message['role'].capitalize()}: {message['content']}" for message in turns)


def summary_request(previous, turns):
    content = f"PREVIOUS SUMMARY:\n{previous or 'None'}\n\nTURNS TO MERGE:\n{format_turns(turns)}"
    return [
        {"role": "system", "content": SUMMARIZER_PROMPT},
        {"role": "user", "content": content},
    ]


def compact_history(history, budget, summarize, count=count_tokens, reserve=SUMMARY_MAX_TOKENS):
    """Replace the oldest user+assistant pairs with one rolling summary.

    `summarize(messages)` returns the summary text. `reserve` is the room
    kept for the summary. The newest pair is never summarized, and the
    first message after the summary is always a user turn.
    """
    if count(history) <= budget:
        return history

    system, previous, turns = split_history(history)
    cut = 0
    while len(turns) - cut > 2 and (cut == 0 or count([system] + turns[cut:]) + reserve > budget):
        cut += 2

    if cut == 0:
        return history

    summary = summarize(summary_request(previous, turns[:cut])).strip()
    summary_message = {"role": "system", "content": f"{SUMMARY_HEADER}\n\n{summary}"}
    return [system, summary_message] + turns[cut:]
