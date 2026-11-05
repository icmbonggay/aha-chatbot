import json

import pytest

import chat
from chat import parse_card


VALID_REPLY = json.dumps({
    "topic": "Photosynthesis",
    "summary": "Plants turn sunlight into food.",
    "analogy": "A solar-powered kitchen in every leaf.",
    "key_terms": [
        {"term": "Chlorophyll", "simple_definition": "Green pigment that catches light."},
        {"term": "Glucose", "simple_definition": "Sugar the plant makes."},
        {"term": "Oxygen", "simple_definition": "Gas the plant releases."},
    ],
    "check_question": "What pigment captures sunlight?",
})
USAGE = {"prompt_tokens": 50, "completion_tokens": 120}


@pytest.mark.parametrize("text, topic", [
    ("/card photosynthesis", "photosynthesis"),
    ("/card bread", "bread"),
    ("/card radar", "radar"),
    ("/card   black holes  ", "black holes"),
])
def test_parse_card_returns_topic(text, topic):
    assert parse_card(text) == topic


@pytest.mark.parametrize("text", ["/card", "/card    "])
def test_parse_card_rejects_missing_topic(text):
    with pytest.raises(ValueError):
        parse_card(text)


def run_chat(monkeypatch, inputs, card_replies):
    """Run the REPL with scripted input and fake card replies.
    Returns what was printed and the history seen by the next normal message."""
    printed = []
    card_calls = []
    seen_history = []
    user_inputs = iter(inputs)

    def fake_send_card(messages, temperature, max_tokens):
        card_calls.append(messages)
        return card_replies[len(card_calls) - 1]

    def fake_send_message(history, temperature, max_tokens):
        seen_history.append([dict(m) for m in history])
        return "ok", USAGE

    monkeypatch.setattr("builtins.input", lambda _: next(user_inputs))
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(map(str, args))))
    monkeypatch.setattr("chat.send_card", fake_send_card)
    monkeypatch.setattr("chat.send_message", fake_send_message)

    chat.main()
    return "\n".join(printed), card_calls, seen_history


def test_card_command_prints_card_and_adds_it_to_history(monkeypatch):
    output, card_calls, seen = run_chat(
        monkeypatch, ["/card photosynthesis", "chlorophyll", "/quit"], [(VALID_REPLY, None, USAGE)])

    assert "SUMMARY" in output and "CHECK YOURSELF" in output
    assert len(card_calls) == 1
    history = seen[0]
    assert history[1] == {"role": "user", "content": "Explain photosynthesis."}
    assert "What pigment captures sunlight?" in history[2]["content"]


def test_card_command_reports_failure_and_leaves_history_alone(monkeypatch):
    output, card_calls, seen = run_chat(
        monkeypatch, ["/card photosynthesis", "hello", "/quit"],
        [("{}", None, USAGE), ("{}", None, USAGE)])

    assert "Couldn't build a valid card" in output
    assert len(card_calls) == 2
    assert len(seen[0]) == 2  # system prompt + "hello" only
