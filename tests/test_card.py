import json

import pytest

import client
from errors import CardError, RefusalError
from explanation import Explanation, card_history_text, format_card, request_card


VALID_CARD = {
    "topic": "Photosynthesis",
    "summary": "Plants turn sunlight, water and air into sugar and oxygen.",
    "analogy": "It is like a solar-powered kitchen inside every leaf.",
    "key_terms": [
        {"term": "Chlorophyll", "simple_definition": "The green pigment that catches light."},
        {"term": "Glucose", "simple_definition": "The sugar the plant makes as food."},
        {"term": "Oxygen", "simple_definition": "The gas the plant releases into the air."},
    ],
    "check_question": "What pigment captures sunlight in plants?",
}
VALID_REPLY = json.dumps(VALID_CARD)

# Missing "analogy" and only two key terms.
BAD_CARD = {k: v for k, v in VALID_CARD.items() if k != "analogy"}
BAD_CARD["key_terms"] = VALID_CARD["key_terms"][:2]
BAD_REPLY = json.dumps(BAD_CARD)

USAGE = {"prompt_tokens": 50, "completion_tokens": 120}
MESSAGES = [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "Create an explanation card about photosynthesis."},
]


def make_fake(replies):
    """A pretend send function that returns scripted replies in order
    and records the messages it was called with."""
    calls = []

    def fake(messages, temperature, max_tokens):
        calls.append([dict(m) for m in messages])
        return replies[len(calls) - 1]

    return fake, calls


def test_valid_reply_returns_card_in_one_call():
    fake, calls = make_fake([(VALID_REPLY, None, USAGE)])
    usage_log = []

    card = request_card(fake, MESSAGES, 0.3, 500, usage_log)

    assert isinstance(card, Explanation)
    assert card.summary == VALID_CARD["summary"]
    assert card.analogy == VALID_CARD["analogy"]
    assert len(card.key_terms) == 3
    assert card.check_question == VALID_CARD["check_question"]
    assert len(calls) == 1
    assert usage_log == [USAGE]


def test_bad_reply_is_repaired_on_retry():
    fake, calls = make_fake([(BAD_REPLY, None, USAGE), (VALID_REPLY, None, USAGE)])
    usage_log = []

    card = request_card(fake, MESSAGES, 0.3, 500, usage_log)

    assert card.analogy == VALID_CARD["analogy"]
    assert len(calls) == 2
    assert len(usage_log) == 2

    retry_messages = calls[1]
    # The retry keeps the original request...
    assert retry_messages[:2] == MESSAGES
    # ...shows the model its own bad reply...
    assert retry_messages[2] == {"role": "assistant", "content": BAD_REPLY}
    # ...and tells it exactly what was wrong.
    error_text = retry_messages[3]["content"]
    assert retry_messages[3]["role"] == "user"
    assert "analogy" in error_text
    assert "key_terms" in error_text


def test_bad_reply_twice_is_reported_after_one_retry():
    fake, calls = make_fake([(BAD_REPLY, None, USAGE), ("not even json", None, USAGE)])

    with pytest.raises(CardError) as error:
        request_card(fake, MESSAGES, 0.3, 500, [])

    assert not isinstance(error.value, RefusalError)
    assert "after one retry" in str(error.value)
    assert len(calls) == 2  # retried once, not more


def test_cut_off_reply_is_treated_as_invalid():
    # What a max_tokens cut-off looks like: half a JSON object.
    fake, calls = make_fake([(VALID_REPLY[:40], None, USAGE), (VALID_REPLY, None, USAGE)])

    card = request_card(fake, MESSAGES, 0.3, 500, [])

    assert card.topic == "Photosynthesis"
    assert len(calls) == 2


def test_refusal_is_not_retried():
    fake, calls = make_fake([(None, "I can't help with that.", USAGE)])

    with pytest.raises(RefusalError) as error:
        request_card(fake, MESSAGES, 0.3, 500, [])

    assert "can't help" in str(error.value)
    assert len(calls) == 1


def test_format_card_shows_the_four_parts_but_not_topic():
    card = Explanation.model_validate(VALID_CARD)

    text = format_card(card)

    for heading in ["SUMMARY", "ANALOGY", "KEY TERMS", "CHECK YOURSELF"]:
        assert heading in text
    assert VALID_CARD["summary"] in text
    assert "- Chlorophyll: The green pigment that catches light." in text
    assert VALID_CARD["check_question"] in text
    assert "Photosynthesis" not in text


def test_history_text_keeps_question_and_drops_key_terms():
    card = Explanation.model_validate(VALID_CARD)

    text = card_history_text(card)

    assert VALID_CARD["summary"] in text
    assert VALID_CARD["analogy"] in text
    assert VALID_CARD["check_question"] in text
    assert "Chlorophyll" not in text
    # Labels in history get copied into later normal replies.
    assert "Analogy:" not in text
    assert "Check question:" not in text


class FakeResponse:
    status_code = 200
    headers = {}
    text = ""

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_send_card_builds_a_structured_outputs_request(monkeypatch):
    sent = {}

    def fake_post(url, headers, json, stream, timeout):
        sent["payload"] = json
        sent["stream"] = stream
        return FakeResponse({
            "choices": [{"message": {"content": VALID_REPLY, "refusal": None}}],
            "usage": USAGE,
        })

    monkeypatch.setattr("client.requests.post", fake_post)

    content, refusal, usage = client.send_card(MESSAGES, 0.3, 500)

    payload = sent["payload"]
    assert sent["stream"] is False
    assert "stream" not in payload
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["schema"] == Explanation.model_json_schema()
    assert (content, refusal, usage) == (VALID_REPLY, None, USAGE)


def test_schema_forbids_extra_fields_everywhere():
    schema = Explanation.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["$defs"]["KeyTerm"]["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
