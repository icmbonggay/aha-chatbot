import csv
from pathlib import Path

from client import send_message
import textstat


temperature = 0
sum_grade_zeroshot = 0
sum_grade_fewshot = 0
results = []

topics = [
    "Photosynthesis",
    "Bluetooth Technology",
    "The Water Cycle",
    "Cloud Storage",
    "Plate Tectonics",
    "QR Codes",
    "Gravity",
    "Wi-Fi Routers",
    "DNA and Genes",
    "GPS Navigation",
    "Cellular Respiration",
    "Two-Factor Authentication (2FA)",
    "Fossils and Stratigraphy",
    "Phishing Scams",
    "The Greenhouse Effect",
    "Solid State Drives (SSDs)",
    "Homomorphic Encryption",
    "Quantum Key Distribution (QKD)",
    "Neuromorphic Computing",
    "Topological Data Analysis (TDA)"
]

for topic in topics:
    zero_shot_prompt = f"Explain this {topic} like you're talking to a five year old."
    messages = [
        {"role": "user", "content": zero_shot_prompt}
    ]
    response, usage = send_message(messages, temperature)
    grade = textstat.flesch_kincaid_grade(response)
    sum_grade_zeroshot += grade
    result = {
        "prompt": "zero-shot",
        "topic": topic,
        "response": response,
        "grade": grade
    }
    results.append(result)


for topic in topics:
    few_shot_prompt = f"""
        #Examples

        <user_query id = 1>
        What is a black hole?
        </user_query>

        <assistant_response id = 1>
        A black hole is like a big vacuum cleaner in space. It pulls everything close to it inside, even light, which is why we can't see it. Imagine if you dropped a toy near a vacuum; it would get sucked in and disappear!
        </assistant_response>

        <user_query id = 2>
        What is an API?
        </user_query>

        <assistant_response id = 2>
        An API is like a waiter in a restaurant. When you want food, you tell the waiter what you want, and then the waiter goes to the kitchen to get it for you. The API helps different computer programs talk to each other and ask for things, just like the waiter helps you get your food.
        </assistant_response>

        Explain this {topic} like you're talking to a five year old.
    """

    messages = [
        {"role": "user", "content": few_shot_prompt}
    ]
    response, usage = send_message(messages, temperature)
    grade = textstat.flesch_kincaid_grade(response)
    sum_grade_fewshot += grade
    result = {
        "prompt": "few-shot",
        "topic": topic,
        "response": response,
        "grade": grade
    }
    results.append(result)


average_zeroshot = sum_grade_zeroshot / len(topics)
average_fewshot = sum_grade_fewshot / len(topics)


print(average_zeroshot)
print(average_fewshot)


output_dir = Path(__file__).parent.parent / "results"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "eli5_eval.csv"

fieldnames = ["prompt", "topic", "response", "grade", "verdict", "notes"]

with open(output_path, "w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

print(f"Saved {len(results)} rows to {output_path}")
