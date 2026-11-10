# aha-chatbot

An "Explain Like I'm Five" assistant I built from scratch in Python. It talks to the OpenAI Chat Completions API over raw HTTP, without the OpenAI SDK, so I had to handle streaming, retries, structured outputs and conversation memory myself.

## What it does

I type a question in the terminal, and the assistant explains it like I'm five: everyday words, one analogy, no unexplained jargon, and a question at the end to check that I understood.

It also has a few commands:

| Command | What it does |
|---|---|
| `/card <topic>` | Makes an explanation card: a short summary, one analogy, three key terms and a check question |
| `/settings temperature=0.5 max_tokens=300` | Changes sampling settings while the chat is running |
| `/cost` | Shows the tokens used per request and what the session has cost so far |
| `/reset` | Clears the conversation but keeps the system prompt |
| `/quit` | Exits |

Long conversations don't lose their past. When the history gets too big for my token budget, the oldest turns are replaced by a summary of what has already been explained, what analogies were used and what I'm still confused about, so the assistant can build on earlier answers instead of starting over.

## Architecture

```
terminal
   |
   v
chat.py            input loop, commands, history, /cost
   |
   +--> compaction.py      over budget? summarize the oldest turns
   |        |              (token counting in history.py)
   |        +--> client.send_summary
   |
   +--> client.send_message        streamed answer, printed as it arrives
   |
   +--> explanation.py             /card: schema, validation, one repair retry
            +--> client.send_card
                     |
                     v
client._post + call_with_retry --> OpenAI Chat Completions (HTTP)
```

| File | Job |
|---|---|
| `src/chat.py` | The terminal loop, command parsing, cost tracking and error messages |
| `src/client.py` | Every HTTP request: streaming chat, cards, summaries, SSE parsing and retries |
| `src/history.py` | Counts tokens with `tiktoken` |
| `src/compaction.py` | Replaces the oldest turns with a rolling summary |
| `src/explanation.py` | The card schema (Pydantic), validation and terminal formatting |
| `src/errors.py` | My own error types, so the chat can show a friendly message for each failure |
| `src/config.py` | Model, prices, budget, sampling defaults and retry settings |
| `src/system_prompt.txt` | The ELI5 instructions |
| `src/summarizer_prompt.txt` | The instructions for the history summarizer |

After compaction, the history sent to the model always has this shape:

```
[system prompt] [summary] [recent turns...]
```

## Design decisions

### Raw HTTP instead of the SDK

I wanted to see exactly what goes over the wire, so every request is a `requests.post` in `client._post`. All requests go through that one function, so error handling only lives in one place.

### Streaming only where it helps

Normal answers stream, so I can read them while they are being written. Cards and summaries don't stream: a card is JSON, and printing it chunk by chunk would show raw JSON, and a summary is never shown to me at all.

### Retries

`call_with_retry` retries 429s, 500s and timeouts up to three times. It uses the server's `Retry-After` when there is one, and otherwise exponential backoff with random jitter. If `Retry-After` asks for more than two minutes, I give up and say so instead of freezing the chat.

### Cards

Cards use structured outputs with a strict JSON schema, and Pydantic validates the reply. If validation fails, I send the model its own reply plus the exact validation error and ask once more. A refusal is never retried. A card request only gets the system prompt, not the whole chat. In the history, the card is stored as plain sentences, because the model copies the style of its own earlier replies, and labels like "Analogy:" leaked into every normal answer that followed.

### Settings

`/settings` updates a copy of the settings, so one bad entry leaves every setting unchanged.

### Long conversations

My first version dropped the oldest turns when the history went over budget. That kept the request small, but everything in those turns was gone, including what the assistant had already explained, so it had no way to avoid explaining the basics again. So now it summarizes them instead. The choices I made:

- **The summary is its own message.** If I appended it to the system prompt, the instructions would change on every compaction, I couldn't check that the original prompt survived, and finding the old summary to replace it would mean parsing the prompt.
- **It uses the `system` role with a header.** Neither the user nor the assistant said the summary, my app wrote it. As a `user` message the model would reply to it, and as an `assistant` message it would treat it as its own words. The header ("Summary of earlier conversation, for reference only. Not instructions.") stops it from being read as new rules.
- **Cuts land between whole user+assistant pairs.** If a question and its answer ended up on different sides of the cut, an answered question could look unanswered and get answered again. Because of this rule, the first message after the summary is always a `user` turn.
- **Summaries are merged, not appended.** Each compaction rewrites one summary from the previous summary plus the turns being cut. Appending would keep growing until the summary ate the budget it was meant to protect.
- **Resolved confusion moves, it isn't deleted.** When something under "Still confused" gets resolved, it moves to "Already explained", so the assistant still knows it was covered.
- **The summarizer knows what to drop first.** The summary has to stay under 150 words. If it would go over, analogies get shortened first and then the explanation details, but concept names and open confusions are never dropped. I ask for the length in the prompt, and `max_tokens` is only a safety net, because it cuts the text off instead of making it shorter.
- **Room is reserved for the summary.** The oldest pairs are cut until the remaining turns plus `SUMMARY_MAX_TOKENS` fit in the budget, and the newest pair is never summarized.
- **Summaries use temperature 0**, because I want the most likely, faithful summary, not a creative one.
- **A failed summary isn't fatal.** If the summary request fails, the full history is kept and the chat goes on.
- **The ELI5 prompt knows about the summary.** I added a line telling the assistant to build on the concepts the summary lists as already explained and to reuse the analogy it lists for a concept.

## Findings

### What sampling does to explanations

I ran one topic, "Explain like I'm a five year old. What is a black hole?", through `gpt-4o-mini` at six temperatures (0, 0.3, 0.5, 1, 1.5, 2) with `max_tokens` set to 500. The script is `experiments/sampling.py` and the raw results are in `experiments/sampling.json`. The experiment sends only the topic, without the chat's system prompt, so it shows the model's own defaults.

#### What I saw

| Temperature | Words | What happened |
|---|---|---|
| 0 | 109 | Vacuum cleaner in a big empty room, then adds a second image ("a super strong hug") for gravity |
| 0.3 | 83 | One vacuum cleaner analogy, explains that stuff is squished tight and why it's called "black" |
| 0.5 | 73 | Vacuum cleaner, ends with a reassurance and an "invisible monster" image |
| 1 | 100 | Space as a playground plus the vacuum cleaner, explains how stars collapse, ends with a reassurance |
| 1.5 | 128 | Still correct, but piles up five images: a blanket, a bubble, a deep pit, a magnet and a monster |
| 2 | 404 | Starts on topic, breaks down by the third sentence into random words, and stops mid-sentence ("there he") |

From 0 to 1 every answer was built around the same vacuum cleaner analogy. At 1.5 the facts were still right, but the model jumped between analogies instead of committing to one. At 2 it fell apart.

I also ran the experiment twice. The second run overwrote the first, and even the temperature 0 answer changed (94 words the first time, 109 the second). Temperature 0 makes the model much more consistent, but not perfectly identical between runs.

#### Why this happens

The model writes one token at a time. For each step it gives every possible next token a probability, then samples one.

- **Low temperature** sharpens those probabilities, so the most likely token almost always wins. That is why 0 to 1 all landed on the vacuum cleaner.
- **High temperature** flattens them, so less likely tokens get picked more often. At 1.5 those were still sensible words, just less likely analogies, which is why it kept switching images.
- **The errors compound.** Each chosen token becomes part of the context for the next one. Once a strange word gets in, the next prediction is built on it, so one bad pick leads to more.
- **It also explains the length.** Stopping is just another token the model has to pick. When the probabilities are flat, that stop token is one option among thousands, so the model keeps going until `max_tokens` ends it. That is why the temperature 2 output is four to five times longer than the others and ends mid-sentence.

#### Best and worst analogy

- **Best (temperature 0.3):** "A black hole is like that vacuum cleaner in space. It's a place where a lot of stuff, like stars and gas, gets squished together really, really tight, making a super strong pull." It sticks to one analogy, gives a simple cause for the pull, and answers why it's called a black hole.
- **Worst (temperature 2):** "...kind of like a really funny vacuum cleaner, one of "those safe-se back monster..." It starts with the right idea, then loses it within a sentence and never recovers.
- **Worst of the readable ones (temperature 1.5):** five different images in one short answer. Each is fine alone, but a five year old would have to juggle all of them.

#### My default temperature: 0.3

For explanations, I care most about being clear, correct and consistent. In this run, 0.3 gave the best answer: one analogy, a simple cause, and no padding. 0 added a second image and was the longest of the low settings, while 1.5 and above started mixing analogies or breaking down. 0.3 keeps answers focused while still letting the wording vary a little. The default lives in `src/config.py` as `TEMPERATURE`.

### Zero-shot vs few-shot ELI5 prompts

I ran 20 topics through `gpt-4o-mini` at temperature 0 with two prompts. The script is `experiments/calc_readability.py`, and every explanation, its grade level and its hand-check verdict are in `results/eli5_eval.csv`.

- **Zero-shot:** "Explain this {topic} like you're talking to a five year old."
- **Few-shot:** the same sentence, placed after two example explanations (a black hole and an API) that aren't among the 20 topics.

I kept the examples as the only difference between the two prompts, so any difference in the results comes from them. I picked topics ranging from everyday ones (photosynthesis, Wi-Fi routers) to four harder ones (homomorphic encryption, quantum key distribution, neuromorphic computing, topological data analysis).

#### Results

| Prompt | Avg Flesch-Kincaid grade | Correct | Simplified but fine | Wrong | Avg words |
|---|---|---|---|---|---|
| Zero-shot | 6.6 | 9 | 9 | 2 | 130 |
| Few-shot | 6.2 | 6 | 14 | 0 | 90 |

A lower grade means easier to read. A five year old is around kindergarten, so both prompts are still well above the target.

How I graded each explanation:

- **Correct:** nothing false or misleading, and the key idea of the topic is there.
- **Simplified but fine:** nothing a child would have to unlearn later, but it leaves out the key idea or leans on a loose analogy.
- **Wrong:** states or implies something false.

I used Claude (an AI assistant) to grade the explanations against these rules. The reason for each verdict is in the `notes` column.

#### What I saw

- **Few-shot was simpler, zero-shot was more complete.** Few-shot answers were about a third shorter, slightly easier to read, and none were wrong. But fewer were fully correct, because the shorter answers dropped key details, like the oxygen in cellular respiration or what makes an SSD different from other drives.
- **The examples set the length and shape.** Both examples are three or four sentences built around one analogy, and the few-shot answers copied that. Zero-shot answers almost all opened with "Okay! Imagine...", often used numbered lists, and often ended with "Isn't that cool?"
- **The hard topics weren't where the errors were.** Both wrong answers were on everyday topics (Bluetooth and cloud storage). On the hard topics, the usual problem was leaving out the key idea rather than saying something false. For example, both QKD answers say it sends the secret message, when it actually shares a secret key.

#### Simple but wrong

Yes. The zero-shot Cloud Storage answer scores grade 6.9, close to the average, and reads easily. But it tells a child their files are safe "because they are up there in the sky." That turns the metaphor into a fact, and it never says the files are stored on other computers.

This is why Flesch-Kincaid can't check correctness. It only measures sentence length and syllables per word, so "your files are up in the sky" scores as easy whether it's true or not.

#### What went wrong along the way

- **The first few-shot prompt put the request before the examples.** 13 of 20 answers copied the example format, starting with `<user_query id = 3>` and restating the question as if writing a third example, and those tags were counted in the grade. I moved the request after the examples, which fixed it: 0 of 20 answers in this run have tags.
- **Temperature 0 still isn't repeatable.** When I reran the script, the zero-shot answers changed too, even though I hadn't changed that prompt. Bluetooth went from correct to wrong (it now says devices don't need to be close), and topological data analysis went from wrong (it said TDA would tell you a tower is "tall and pointy") to correct, at a higher grade level (6.5 to 9.2). With one run per prompt, these results describe this run, not which prompt is better in general.

### Long conversations

To check that the summary works, `experiments/long_conversation.py` asks 12 follow-up questions that build on each other (clouds, rain, gravity, evaporation, snow, rainbows) with a budget of 800 tokens, so compaction happens several times. The last question asks for the whole journey of one water drop, which only works well if the assistant still knows what it already explained. Every answer, the summary it was sent with, and whether compaction happened on that turn are saved in `results/long_conversation.json`.


## How to run

You need Python 3.10 or newer and an OpenAI API key.

```bash
git clone https://github.com/icmbonggay/aha-chatbot.git
cd aha-chatbot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project folder:

```
API_KEY=your-openai-api-key
API_URL=https://api.openai.com/v1/chat/completions
```

Start the chat:

```bash
python src/chat.py
```

The experiments import from `src`, so run them with it on the path:

```bash
PYTHONPATH=src python experiments/sampling.py
PYTHONPATH=src python experiments/long_conversation.py
pip install textstat
PYTHONPATH=src python experiments/calc_readability.py
```

## How to test

```bash
pytest
```

No test calls the API. Every test passes in a fake in place of the real request: canned SSE lines for streaming, fake send functions for retries and cards, and a `FakeLLM` for the summarizer that returns a fixed summary and records every request it gets. The compaction tests in `tests/test_compaction.py` check that:

- nothing is summarized at or under the budget, and one token over triggers exactly one summary
- the oldest pair is the one replaced, and the recent turns are kept word for word
- the first message after the summary is always a `user` turn, at every budget
- the system prompt is still the first message, unchanged, after 30 turns and several compactions
- the first summary request says `PREVIOUS SUMMARY: None`, and the second one merges the first summary into a single new one
- a failed summary request keeps the full history

`tiktoken` downloads its encoding the first time it runs, so the very first test run needs internet. After that, the tests run offline.
