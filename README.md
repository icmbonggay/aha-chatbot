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
