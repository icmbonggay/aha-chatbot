import pytest
import requests

import client
from errors import APIError, NoResponseError


def make_fake(outcomes):
    """Build a pretend send_message that follows a script.

    Each item in `outcomes` is what happens on one call:
    an exception gets raised, anything else gets returned.
    """
    calls = []

    def fake(history, temperature, max_tokens):
        calls.append(1)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return fake, calls


@pytest.fixture
def sleeps(monkeypatch):
    """Replace time.sleep so tests never wait, and record every wait."""
    recorded = []
    monkeypatch.setattr("client.time.sleep", lambda seconds: recorded.append(seconds))
    return recorded



def test_429_is_retried_then_succeeds(sleeps):
    fake, calls = make_fake([APIError("rate limited", 429), ("hello", {})])

    result = client.call_with_retry(fake, [], 0.3, 500)

    assert result == ("hello", {})
    assert len(calls) == 2
    assert len(sleeps) == 1


def test_500_is_retried_then_succeeds(sleeps):
    fake, calls = make_fake([APIError("server error", 500), ("hello", {})])

    result = client.call_with_retry(fake, [], 0.3, 500)

    assert result == ("hello", {})
    assert len(calls) == 2


def test_timeout_is_retried_then_succeeds(sleeps):
    fake, calls = make_fake([NoResponseError("timed out"), ("hello", {})])

    result = client.call_with_retry(fake, [], 0.3, 500)

    assert result == ("hello", {})
    assert len(calls) == 2


def test_401_is_not_retried(sleeps):
    fake, calls = make_fake([APIError("bad key", 401)])

    with pytest.raises(APIError) as error:
        client.call_with_retry(fake, [], 0.3, 500)

    assert error.value.status_code == 401
    assert len(calls) == 1
    assert sleeps == []


def test_gives_up_after_max_retries(sleeps):
    always_500 = [APIError("server error", 500)] * (client.MAX_RETRIES + 1)
    fake, calls = make_fake(always_500)

    with pytest.raises(APIError):
        client.call_with_retry(fake, [], 0.3, 500)

    assert len(calls) == client.MAX_RETRIES + 1
    assert len(sleeps) == client.MAX_RETRIES



def test_wait_uses_retry_after(sleeps):
    fake, calls = make_fake([APIError("rate limited", 429, retry_after=2), ("hello", {})])

    client.call_with_retry(fake, [], 0.3, 500)

    assert sleeps == [2]


def test_retry_after_too_long_gives_up(sleeps):
    too_long = client.MAX_RETRY_AFTER + 1
    fake, calls = make_fake([APIError("rate limited", 429, retry_after=too_long)])

    with pytest.raises(APIError):
        client.call_with_retry(fake, [], 0.3, 500)

    assert len(calls) == 1
    assert sleeps == []



class FakeResponse:
    def __init__(self, status_code, headers):
        self.status_code = status_code
        self.headers = requests.structures.CaseInsensitiveDict(headers)
        self.text = "error"

    def json(self):
        return {"error": {"message": "error"}}


def test_send_message_reads_retry_after_header(monkeypatch):
    monkeypatch.setattr(
        "client.requests.post",
        lambda *args, **kwargs: FakeResponse(429, {"Retry-After": "2"}),
    )

    with pytest.raises(APIError) as error:
        client.send_message([], 0.3)

    assert error.value.status_code == 429
    assert error.value.retry_after == 2


def test_send_message_turns_timeout_into_no_response_error(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise requests.exceptions.ReadTimeout("server went quiet")

    monkeypatch.setattr("client.requests.post", raise_timeout)

    with pytest.raises(NoResponseError) as error:
        client.send_message([], 0.3)

    assert error.value.status_code is None
