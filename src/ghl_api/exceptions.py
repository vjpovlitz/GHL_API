class GHLAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class GHLAuthError(GHLAPIError):
    pass


class GHLRateLimitError(GHLAPIError):
    def __init__(self, message: str, retry_after: float | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
