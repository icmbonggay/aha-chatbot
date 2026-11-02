from client import send_message
from config import MODEL, MAX_TOKENS
import json
from pathlib import Path

temperatures = [0, 0.3, 0.5, 1, 1.5, 2]
TOPIC = "Explain like I'm a five year old. What is a black hole?"

output_path = Path(__file__).parent / "sampling.json"

messages = [
    {"role": "user", "content": TOPIC}
]
results = []

for i in temperatures:
    print(f"Temperature at {i}")
    reply, usage = send_message(messages, i)
    print("==============================================================")
    result = {
        "topic": TOPIC,
        "model": MODEL,
        "temperature": i,
        "max_tokens": MAX_TOKENS,
        "output": reply
    }

    results.append(result)
    
with open(output_path, "w", encoding="utf-8") as file:
    json.dump(results, file, indent=4, ensure_ascii=False)
