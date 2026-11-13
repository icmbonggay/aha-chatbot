import os
import requests
import json
import time
import random
from dotenv import load_dotenv
from errors import APIError, NoResponseError
from explanation import card_response_format
from config import (MODEL, MAX_TOKENS, TIMEOUTS, MAX_RETRIES, RETRYABLE_STATUS,
                    BASE_DELAY, BACKOFF_CAP, MAX_RETRY_AFTER)

load_dotenv()

api_key = os.getenv("API_KEY")
url = os.getenv("API_URL")
DONE = object()

def _post(payload, stream=False):
    """Send one request to the API and return the response.

    Shared by every request type, so error handling lives in one place.
    Raises APIError for a non-200 reply and NoResponseError when the
    server can't be reached.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, stream=stream, timeout=TIMEOUTS)
    except requests.exceptions.RequestException as e:
        raise _network_error(e) from e

    if response.status_code != 200:
        raw_retry_after = response.headers.get("Retry-After")
        retry_after = None
        if raw_retry_after is not None:
            retry_after = int(raw_retry_after)
        try:
            error_json = response.json()
            error_message = error_json.get("error", {}).get("message", response.text)
        except Exception:
            error_message = response.text

        raise APIError(error_message, response.status_code, retry_after)

    return response


def _network_error(e):
    """Turn a requests exception into one of our own errors."""
    no_response = (
        requests.exceptions.ReadTimeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.ConnectTimeout,
    )
    if isinstance(e, no_response):
        return NoResponseError(f"No usable response error: {str(e)}")
    return APIError(f"Network error: {str(e)}", 500)


def send_message(messages, temperature, max_tokens=MAX_TOKENS, echo=True):
    """Stream a reply and return (text, usage).

    echo=True prints the reply as it arrives (the terminal chat).
    echo=False stays quiet, for callers with no terminal, like the
    browser extension server.
    """
    pieces = []
    usage = {}
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    response = _post(payload, stream=True)

    # The connection can still drop while chunks are arriving,
    # so reading the stream needs its own error handling.
    try:
        for line in response.iter_lines():
            parsed = parse_sse(line)

            if parsed is None:
                continue
            elif parsed is DONE:
                if echo:
                    print("\n")
                return "".join(pieces), usage
            elif isinstance(parsed, dict):
                usage = parsed
            else:
                if echo:
                    print(parsed, end="", flush=True)
                pieces.append(parsed)

    except requests.exceptions.RequestException as e:
        raise _network_error(e) from e

    except (KeyError, IndexError) as e:
        raise APIError(f"Malformed response from API: {str(e)}", 500) from e


def send_card(messages, temperature, max_tokens=MAX_TOKENS):
    """Ask for an explanation card. Returns (content, refusal, usage).

    No streaming here: the reply is JSON, so printing it chunk by chunk
    would show raw JSON to the user. Validation happens in the caller.
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": card_response_format(),
    }

    response = _post(payload)

    try:
        data = response.json()
        message = data["choices"][0]["message"]
        return message.get("content"), message.get("refusal"), data.get("usage", {})
    except (ValueError, KeyError, IndexError) as e:
        raise APIError(f"Malformed response from API: {str(e)}", 500) from e


def send_summary(messages, temperature, max_tokens=MAX_TOKENS):
    """Ask for a history summary. Returns (content, usage) without streaming."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    response = _post(payload)

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"] or "", data.get("usage", {})
    except (ValueError, KeyError, IndexError) as e:
        raise APIError(f"Malformed response from API: {str(e)}", 500) from e


def parse_sse(line):
    if line == b'':
        return None
    decoded_line = line.decode("utf-8")
    data_value = decoded_line.removeprefix("data:").strip()

    if data_value == "[DONE]":
        return DONE

    try:
        parsed_data = json.loads(data_value)
        if "usage" in parsed_data and parsed_data["usage"] is not None:
            return parsed_data["usage"]
        if "choices" in parsed_data and parsed_data["choices"] and  "content" in parsed_data["choices"][0]["delta"] :
            output = parsed_data["choices"][0]["delta"]["content"]
            return output
    except json.JSONDecodeError:
        return None   


def call_with_retry(function, history, temperature, max_tokens):
    calls = 0
    while calls <= MAX_RETRIES:
        try:
            return function(history, temperature, max_tokens)
        except APIError as e:
            if e.status_code not in RETRYABLE_STATUS:
                raise
            if e.retry_after is not None and e.retry_after > MAX_RETRY_AFTER:
                raise
            if calls == MAX_RETRIES:
                raise
            retry_after = e.retry_after

        calls += 1
        if retry_after is not None:
            time.sleep(retry_after)
        else:
            time.sleep(random.uniform(0, min(BACKOFF_CAP, BASE_DELAY * 2 ** calls)))
