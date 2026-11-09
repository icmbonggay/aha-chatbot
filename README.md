# chat-from-scratch

## What sampling does to explanations

I ran one topic, "Explain like I'm a five year old. What is a black hole?", through `gpt-4o-mini` at six temperatures (0, 0.3, 0.5, 1, 1.5, 2) with `max_tokens` set to 500. The script is `experiments/sampling.py` and the raw results are in `experiments/sampling.json`. The experiment sends only the topic, without the chat's system prompt, so it shows the model's own defaults.

### What I saw

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

### Why this happens

The model writes one token at a time. For each step it gives every possible next token a probability, then samples one.

- **Low temperature** sharpens those probabilities, so the most likely token almost always wins. That is why 0 to 1 all landed on the vacuum cleaner.
- **High temperature** flattens them, so less likely tokens get picked more often. At 1.5 those were still sensible words, just less likely analogies, which is why it kept switching images.
- **The errors compound.** Each chosen token becomes part of the context for the next one. Once a strange word gets in, the next prediction is built on it, so one bad pick leads to more.
- **It also explains the length.** Stopping is just another token the model has to pick. When the probabilities are flat, that stop token is one option among thousands, so the model keeps going until `max_tokens` ends it. That is why the temperature 2 output is four to five times longer than the others and ends mid-sentence.

### Best and worst analogy

- **Best (temperature 0.3):** "A black hole is like that vacuum cleaner in space. It's a place where a lot of stuff, like stars and gas, gets squished together really, really tight, making a super strong pull." It sticks to one analogy, gives a simple cause for the pull, and answers why it's called a black hole.
- **Worst (temperature 2):** "...kind of like a really funny vacuum cleaner, one of "those safe-se back monster..." It starts with the right idea, then loses it within a sentence and never recovers.
- **Worst of the readable ones (temperature 1.5):** five different images in one short answer. Each is fine alone, but a five year old would have to juggle all of them.

### My default temperature: 0.3

For explanations, I care most about being clear, correct and consistent. In this run, 0.3 gave the best answer: one analogy, a simple cause, and no padding. 0 added a second image and was the longest of the low settings, while 1.5 and above started mixing analogies or breaking down. 0.3 keeps answers focused while still letting the wording vary a little. The default lives in `src/config.py` as `TEMPERATURE`.

## Zero-shot vs few-shot ELI5 prompts

I ran 20 topics through `gpt-4o-mini` at temperature 0 with two prompts. The script is `experiments/calc_readability.py`, and every explanation, its grade level and its hand-check verdict are in `results/eli5_eval.csv`.

- **Zero-shot:** "Explain this {topic} like you're talking to a five year old."
- **Few-shot:** the same sentence, placed after two example explanations (a black hole and an API) that aren't among the 20 topics.

I kept the examples as the only difference between the two prompts, so any difference in the results comes from them. I picked topics ranging from everyday ones (photosynthesis, Wi-Fi routers) to four harder ones (homomorphic encryption, quantum key distribution, neuromorphic computing, topological data analysis).

### Results

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

### What I saw

- **Few-shot was simpler, zero-shot was more complete.** Few-shot answers were about a third shorter, slightly easier to read, and none were wrong. But fewer were fully correct, because the shorter answers dropped key details, like the oxygen in cellular respiration or what makes an SSD different from other drives.
- **The examples set the length and shape.** Both examples are three or four sentences built around one analogy, and the few-shot answers copied that. Zero-shot answers almost all opened with "Okay! Imagine...", often used numbered lists, and often ended with "Isn't that cool?"
- **The hard topics weren't where the errors were.** Both wrong answers were on everyday topics (Bluetooth and cloud storage). On the hard topics, the usual problem was leaving out the key idea rather than saying something false. For example, both QKD answers say it sends the secret message, when it actually shares a secret key.

### Simple but wrong

Yes. The zero-shot Cloud Storage answer scores grade 6.9, close to the average, and reads easily. But it tells a child their files are safe "because they are up there in the sky." That turns the metaphor into a fact, and it never says the files are stored on other computers.

This is why Flesch-Kincaid can't check correctness. It only measures sentence length and syllables per word, so "your files are up in the sky" scores as easy whether it's true or not.

### What went wrong along the way

- **The first few-shot prompt put the request before the examples.** 13 of 20 answers copied the example format, starting with `<user_query id = 3>` and restating the question as if writing a third example, and those tags were counted in the grade. I moved the request after the examples, which fixed it: 0 of 20 answers in this run have tags.
- **Temperature 0 still isn't repeatable.** When I reran the script, the zero-shot answers changed too, even though I hadn't changed that prompt. Bluetooth went from correct to wrong (it now says devices don't need to be close), and topological data analysis went from wrong (it said TDA would tell you a tower is "tall and pointy") to correct, at a higher grade level (6.5 to 9.2). With one run per prompt, these results describe this run, not which prompt is better in general.
