import json
from pathlib import Path

from chat import load_system_prompt, make_summarizer
from client import send_message, call_with_retry
from compaction import compact_history, is_summary
from config import TEMPERATURE, MAX_TOKENS

BUDGET = 800

questions = [
    "What is a cloud?",
    "Why are clouds white?",
    "Why do some clouds turn gray?",
    "What makes the water in clouds fall as rain?",
    "What is gravity?",
    "Why doesn't gravity pull the clouds down too?",
    "Where does the water in clouds come from?",
    "What is evaporation?",
    "Why does it snow instead of rain sometimes?",
    "How do rainbows happen after it rains?",
    "Why are puddles gone the next day?",
    "So what is the whole journey of one water drop, from a puddle back to a puddle?",
]

history = [{"role": "system", "content": load_system_prompt()}]
usage_history = []
summarize = make_summarizer(usage_history)
results = []

for question in questions:
    print(f"\n>>> {question}")
    history.append({"role": "user", "content": question})
    compacted = compact_history(history, BUDGET, summarize)
    was_compacted = compacted is not history
    history = compacted
    summary = history[1]["content"] if is_summary(history[1]) else None
    response, usage = call_with_retry(send_message, history, TEMPERATURE, MAX_TOKENS)
    history.append({"role": "assistant", "content": response})
    results.append({
        "question": question,
        "compacted": was_compacted,
        "summary": summary,
        "messages_sent": len(history) - 1,
        "response": response,
    })

output = Path(__file__).parent.parent / "results" / "long_conversation.json"
output.write_text(json.dumps(results, indent=4), encoding="utf-8")
print(f"\nSaved {len(results)} turns to {output}")
