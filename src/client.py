import os
import requests
import json
import time
import random
from dotenv import load_dotenv
from errors import APIError, NoResponseError
from config import (MODEL, MAX_TOKENS, TIMEOUTS, MAX_RETRIES, RETRYABLE_STATUS,
                    BASE_DELAY, BACKOFF_CAP, MAX_RETRY_AFTER)

load_dotenv()

api_key = os.getenv("API_KEY")
url = os.getenv("API_URL")
DONE = object()

def send_message(messages, temperature, max_tokens=MAX_TOKENS):
    pieces = []
    usage = {}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True}, 
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=TIMEOUTS)
        

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

        for line in response.iter_lines():
            # print(line)
            parsed = parse_sse(line)

            if parsed is None:
                continue
            elif parsed is DONE:
                print("\n")
                return "".join(pieces), usage
            elif isinstance(parsed, dict):
                usage = parsed
            else:
                print(parsed, end="", flush=True)
                pieces.append(parsed)
        
       
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
        raise NoResponseError(f"No usable response error: {str(e)}") from e
           
    except requests.exceptions.RequestException as e:
        raise APIError(f"Network error: {str(e)}", 500) from e
        
    except (KeyError, IndexError) as e:
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
