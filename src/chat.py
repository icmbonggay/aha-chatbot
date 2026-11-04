from history import trim_history
from pathlib import Path
from client import send_message, call_with_retry
from config import INPUT_RATE, OUTPUT_RATE, BUDGET, TEMPERATURE, MAX_TOKENS
from errors import APIError, NoResponseError



def load_system_prompt():
    prompt_path = Path(__file__).parent / "system_prompt.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()
    else:
        return "You are a helpful assistant"

def calculate_cost(usage_history):
    input_tokens = [i["prompt_tokens"] for i in usage_history]
    output_tokens = [i["completion_tokens"] for i in usage_history]
    session_cost = sum(input_tokens) * INPUT_RATE + sum(output_tokens) * OUTPUT_RATE
    return input_tokens, output_tokens, session_cost

def parse_settings(text, settings):
    """Return a new settings dict updated from '/settings key=value ...'.

    Works on a copy, so one bad entry leaves every setting unchanged.
    """
    updated = dict(settings)
    for part in text.split()[1:]:
        if "=" not in part:
            raise ValueError(f"Expected key=value, got '{part}'")
        key, value = part.split("=", 1)
        if key == "temperature":
            number = float(value)
            if not 0 <= number <= 2:
                raise ValueError("temperature must be between 0 and 2")
            updated["temperature"] = number
        elif key == "max_tokens":
            number = int(value)
            if number < 1:
                raise ValueError("max_tokens must be at least 1")
            updated["max_tokens"] = number
        else:
            raise ValueError(f"Unknown setting '{key}'. Use temperature or max_tokens")
    return updated


def friendly_error(e):
    if isinstance(e, NoResponseError):
        return "Couldn't reach the server. Check your internet connection and try again."
    if e.status_code == 401:
        return "Your API key was rejected. Check API_KEY in your .env file."
    if e.status_code == 429:
        if e.retry_after:
            return f"Rate limit reached. Try again in about {e.retry_after} seconds."
        return "Rate limit reached. Wait a moment and try again."
    if e.status_code == 500:
        return "The server had a problem. Try again in a moment."
    return f"Request failed ({e.status_code}). Try again."

def main(): 
    system_prompt = load_system_prompt()
    history = [{"role": "system", "content": system_prompt}]
    usage_history = []
    settings = {"temperature": TEMPERATURE, "max_tokens": MAX_TOKENS}

    while True:
        text = input("Enter your prompt: ")
        
        match text:
            case "/quit":
                break
            case "/reset":
                history = [history[0]]
            case "/cost":
                input_tokens, output_tokens, session_cost = calculate_cost(usage_history)
                print("Input tokens: ", input_tokens)
                print("Output tokens: ", output_tokens)
                print("Session Cost: ","{:.10f}".format(session_cost))
            case _ if text == "/settings" or text.startswith("/settings "):
                try:
                    settings = parse_settings(text, settings)
                    print("Settings:", settings)
                except ValueError as e:
                    print("Settings not changed:", e)
            case _:
                history.append({"role": "user", "content": text})
                history = trim_history(history, BUDGET)
                try:
                    response, usage = call_with_retry(send_message, history, settings["temperature"], settings["max_tokens"])
                except APIError as e:
                    history.pop()
                    print(friendly_error(e))
                    print("\n")
                else:
                    history.append({"role": "assistant", "content": response})
                    usage_history.append(usage)



if __name__ == "__main__":
    main()

