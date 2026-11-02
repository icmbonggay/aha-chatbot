import chat


def test_chat_history_returns_correct_length(monkeypatch):
    captured_histories = []
    temperature = 1

    def mock_send_message(history, temperature, max_tokens):
        captured_histories.append([dict(msg) for msg in history])
        return "Mock response", {"prompt_tokens": 10, "completion_tokens": 5}

    user_inputs = iter([
        "Hi. my name is Alice! What is a server?", 
        "/reset", 
        "What is my name?", 
        "/quit"
    ])

    monkeypatch.setattr("builtins.input", lambda _: next(user_inputs))
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)
    monkeypatch.setattr("chat.send_message", mock_send_message)

    chat.main()

    for h in captured_histories:
        assert h[0]["role"] == "system"

    assert len(captured_histories[0]) == 2
    assert len(captured_histories[1]) == 2


    


    




