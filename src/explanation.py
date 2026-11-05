import textwrap

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from errors import CardError, RefusalError


class KeyTerm(BaseModel):
  term: str
  simple_definition: str

  model_config = ConfigDict(extra="forbid")


class Explanation(BaseModel):
  topic: str
  summary: str = Field(description="Two or three sentences explaining the topic simply.")
  analogy: str = Field(description="One everyday analogy that makes the topic click.")
  key_terms: list[KeyTerm] = Field(min_length=3, max_length=3)
  check_question: str = Field(description="One question the learner can answer to check understanding.")

  model_config = ConfigDict(extra="forbid")


def card_response_format():
  """The response_format block that asks the API for an Explanation."""
  return {
    "type": "json_schema",
    "json_schema": {
      "name": "explanation_card",
      "strict": True,
      "schema": Explanation.model_json_schema(),
    },
  }


def card_request(topic):
  """The user message sent to the model when asking for a card."""
  return {"role": "user", "content": f"Create an explanation card about {topic}."}


def request_card(send, messages, temperature, max_tokens, usage_log):
  """Ask for a card, validate it, and retry once with the validation error.

  `send(messages, temperature, max_tokens)` must return
  (content, refusal, usage). Passing it in lets tests use fake replies.
  Every usage dict is appended to `usage_log` so /cost stays accurate.

  Raises RefusalError if the model declines (never retried) and
  CardError if the reply is still invalid after the retry.
  """
  content, refusal, usage = send(messages, temperature, max_tokens)
  if usage:
    usage_log.append(usage)
  if refusal:
    raise RefusalError(refusal)

  try:
    return Explanation.model_validate_json(content or "")
  except ValidationError as error:
    first_error = error

  # Show the model its own bad reply plus exactly what was wrong with it.
  repair_messages = messages + [
    {"role": "assistant", "content": content or ""},
    {
      "role": "user",
      "content": (
        "Your reply did not match the required card format. "
        f"Validation error:\n{first_error}\n"
        "Send the complete card again with these problems fixed."
      ),
    },
  ]

  content, refusal, usage = send(repair_messages, temperature, max_tokens)
  if usage:
    usage_log.append(usage)
  if refusal:
    raise RefusalError(refusal)

  try:
    return Explanation.model_validate_json(content or "")
  except ValidationError as error:
    raise CardError(
      f"Couldn't build a valid card after one retry. Last error:\n{error}"
    ) from error


def _wrap(text, first_indent="  ", next_indent="  ", width=72):
  return textwrap.fill(text, width=width, initial_indent=first_indent, subsequent_indent=next_indent)


def format_card(card):
  """Readable terminal version of the card. The topic is left out on
  purpose: the user just typed it."""
  lines = ["", "SUMMARY", _wrap(card.summary), "", "ANALOGY", _wrap(card.analogy), "", "KEY TERMS"]
  for key_term in card.key_terms:
    # Wrapped lines line up under the term, not under the dash.
    lines.append(_wrap(f"- {key_term.term}: {key_term.simple_definition}", next_indent="    "))
  lines += ["", "CHECK YOURSELF", _wrap(card.check_question), ""]
  return "\n".join(lines)


def card_history_text(card):
  """Compact text stored in chat history. Key terms are left out to save
  tokens; the check question stays so the model can grade an answer."""
  return (
    f"{card.summary}\n\n"
    f"Analogy: {card.analogy}\n\n"
    f"Check question: {card.check_question}"
  )
