from client import send_message
from config import TEMPERATURE

messages = [
    {"role": "user", "content": "Write a haiku about coding. It should rhyme"}
]

response, usage = send_message(messages, TEMPERATURE)
print(usage)
