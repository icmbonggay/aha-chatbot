class APIError(Exception):
  def __init__(self, message, status_code=None, retry_after=None):
    super().__init__(message)
    self.message = message
    self.status_code = status_code
    self.retry_after = retry_after


class NoResponseError(APIError):

  def __init__(self, message="No usable response."):
    super().__init__(message)

class CardError(Exception):
  """The model couldn't produce a valid explanation card."""


class RefusalError(CardError):
  """The model declined to make the card. Retrying won't help."""
