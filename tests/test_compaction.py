import pytest

import chat
from compaction import SUMMARY_HEADER, compact_history, is_summary
from errors import APIError
from history import count_tokens

SYSTEM = {"role": "system", "content": "Explain things like the user is five."}


class FakeLLM:
    def __init__(self, reply="Already explained: None\nAnalogies used: None\nStill confused: None"):
        self.reply = reply
        self.calls = []

    def __call__(self, messages):
        self.calls.append([dict(message) for message in messages])
        return self.reply


def make_history(pairs, start=1):
    history = [dict(SYSTEM)]
    for n in range(start, start + pairs):
        history.append({"role": "user", "content": f"Question {n}: why does thing {n} happen?"})
        history.append({"role": "assistant", "content": f"Answer {n}: thing {n} happens because of reason {n}."})
    return history


def summarized_turns(call):
    return call[1]["content"].split("TURNS TO MERGE:\n", 1)[1]


def test_under_budget_does_not_summarize():
    history = make_history(5)
    llm = FakeLLM()

    result = compact_history(history, count_tokens(history) + 1, llm, reserve=0)

    assert result == history
    assert llm.calls == []


def test_exactly_at_budget_does_not_summarize():
    history = make_history(5)
    llm = FakeLLM()

    result = compact_history(history, count_tokens(history), llm, reserve=0)

    assert result == history
    assert llm.calls == []


def test_one_token_over_budget_summarizes_once():
    history = make_history(5)
    llm = FakeLLM()

    compact_history(history, count_tokens(history) - 1, llm, reserve=0)

    assert len(llm.calls) == 1


def test_oldest_pair_is_replaced_and_recent_turns_kept():
    history = make_history(5)
    llm = FakeLLM("clouds were explained")

    result = compact_history(history, count_tokens(history) - 1, llm, reserve=0)

    assert result[1] == {"role": "system", "content": f"{SUMMARY_HEADER}\n\nclouds were explained"}
    assert result[2:] == history[3:]
    assert "Question 1" in summarized_turns(llm.calls[0])
    assert "Question 2" not in summarized_turns(llm.calls[0])


@pytest.mark.parametrize("pending_user", [False, True])
def test_first_message_after_summary_is_user(pending_user):
    history = make_history(8)
    if pending_user:
        history.append({"role": "user", "content": "One more question?"})

    for budget in range(1, count_tokens(history)):
        result = compact_history(history, budget, FakeLLM(), reserve=0)
        if is_summary(result[1]):
            assert result[2]["role"] == "user"


def test_newest_pair_is_never_summarized():
    history = make_history(5)

    result = compact_history(history, 1, FakeLLM())

    assert result[2:] == history[-2:]


def test_nothing_happens_when_only_the_newest_pair_is_left():
    history = make_history(1)
    llm = FakeLLM()

    result = compact_history(history, 1, llm)

    assert result == history
    assert llm.calls == []


def test_result_fits_budget_when_summary_fits_reserve():
    history = make_history(20)
    budget = 300

    result = compact_history(history, budget, FakeLLM("short summary"), reserve=60)

    assert count_tokens(result) <= budget


def test_system_prompt_survives_many_compactions():
    history = [dict(SYSTEM)]
    llm = FakeLLM()

    for n in range(30):
        history.append({"role": "user", "content": f"Question {n}: why does thing {n} happen?"})
        history = compact_history(history, 300, llm, reserve=60)
        history.append({"role": "assistant", "content": f"Answer {n}: thing {n} happens because of reason {n}."})

        assert history[0] == SYSTEM
        assert sum(is_summary(message) for message in history) <= 1

    assert len(llm.calls) > 1


def test_first_summary_request_has_no_previous_summary():
    history = make_history(5)
    llm = FakeLLM()

    compact_history(history, count_tokens(history) - 1, llm, reserve=0)

    assert llm.calls[0][0]["role"] == "system"
    assert llm.calls[0][1]["content"].startswith("PREVIOUS SUMMARY:\nNone\n")


def test_second_compaction_merges_previous_summary():
    history = make_history(3)
    first = compact_history(history, count_tokens(history) - 1, FakeLLM("first summary"), reserve=0)
    longer = first + make_history(3, start=4)[1:]
    llm = FakeLLM("second summary")

    second = compact_history(longer, count_tokens(longer) - 1, llm, reserve=0)

    request = llm.calls[0][1]["content"]
    assert request.startswith("PREVIOUS SUMMARY:\nfirst summary\n")
    assert SUMMARY_HEADER not in summarized_turns(llm.calls[0])
    assert sum(is_summary(message) for message in second) == 1
    assert second[1]["content"].endswith("second summary")


def test_original_history_is_not_changed():
    history = make_history(5)
    original = [dict(message) for message in history]

    compact_history(history, 1, FakeLLM())

    assert history == original


def test_failed_summary_keeps_full_history(monkeypatch):
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat, "BUDGET", 1)
    history = make_history(5)

    def failing_summarize(messages):
        raise APIError("server error", 500)

    assert chat.compact(history, failing_summarize) == history
