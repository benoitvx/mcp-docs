"""Typed exception hierarchy for Docs API errors."""


class DocsAPIError(Exception):
    """Base exception for Docs API errors.

    ``body`` carries the (truncated) raw response text from the API to help
    server-side diagnostics. It must never be returned to the LLM caller —
    user-facing tool responses keep status-code-only messages (ANSSI).
    """

    def __init__(self, status_code: int, message: str, body: str | None = None) -> None:
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(message)


class DocsAuthError(DocsAPIError):
    """Raised on HTTP 401 — invalid or expired credentials."""

    def __init__(self, message: str = "Authentication failed", body: str | None = None) -> None:
        super().__init__(401, message, body)


class DocsPermissionError(DocsAPIError):
    """Raised on HTTP 403 — insufficient permissions."""

    def __init__(self, message: str = "Access denied", body: str | None = None) -> None:
        super().__init__(403, message, body)


class DocsNotFoundError(DocsAPIError):
    """Raised on HTTP 404 — resource not found."""

    def __init__(self, message: str = "Resource not found", body: str | None = None) -> None:
        super().__init__(404, message, body)


class DocsValidationError(DocsAPIError):
    """Raised on HTTP 422 — invalid request data."""

    def __init__(self, message: str = "Validation error", body: str | None = None) -> None:
        super().__init__(422, message, body)


class DocsRateLimitError(DocsAPIError):
    """Raised on HTTP 429 — rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", body: str | None = None) -> None:
        super().__init__(429, message, body)
