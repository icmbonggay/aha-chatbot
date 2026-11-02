import pytest

import chat
from chat import parse_settings

DEFAULTS = {"temperature": 0.3, "max_tokens": 500}


def test_updates_both_settings():
    result = parse_settings("/settings temperature=0.7 max_tokens=50", DEFAULTS)
    assert result == {"temperature": 0.7, "max_tokens": 50}


def test_updates_only_the_named_setting():
    result = parse_settings("/settings max_tokens=20", DEFAULTS)
    assert result == {"temperature": 0.3, "max_tokens": 20}


def test_no_arguments_keeps_settings():
    assert parse_settings("/settings", DEFAULTS) == DEFAULTS


@pytest.mark.parametrize("text", [
    "/settings temperature=hot",
    "/settings temperature=3",
    "/settings max_tokens=0",
    "/settings max_tokens=1.5",
    "/settings top_p=0.9",
    "/settings temperature",
])
def test_bad_input_raises(text):
    with pytest.raises(ValueError):
        parse_settings(text, DEFAULTS)


def test_bad_input_does_not_change_original():
    settings = dict(DEFAULTS)
    with pytest.raises(ValueError):
        parse_settings("/settings temperature=0.9 max_tokens=abc", settings)
    assert settings == DEFAULTS


def test_settings_change_live_in_chat(monkeypatch):
    sent = []

    def mock_send_message(history, temperature, max_tokens):
        sent.append((temperature, max_tokens))
        return "Mock response", {"prompt_tokens": 10, "completion_tokens": 5}

    user_inputs = iter([
        "First question",
        "/settings temperature=1.2 max_tokens=40",
        "Second question",
        "/settings max_tokens=oops",
        "Third question",
        "/quit",
    ])

    monkeypatch.setattr("builtins.input", lambda _: next(user_inputs))
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)
    monkeypatch.setattr("chat.send_message", mock_send_message)
    monkeypatch.setattr("chat.TEMPERATURE", 0.3)
    monkeypatch.setattr("chat.MAX_TOKENS", 500)

    chat.main()

    assert sent == [(0.3, 500), (1.2, 40), (1.2, 40)]
