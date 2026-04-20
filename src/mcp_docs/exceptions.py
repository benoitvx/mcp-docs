"""Typed exception hierarchy for Docs API errors."""


class DocsAPIError(Exception):
    """Base exception for Docs API errors."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class DocsAuthError(DocsAPIError):
    """Raised on HTTP 401 — invalid or expired credentials."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(401, message)


class DocsPermissionError(DocsAPIError):
    """Raised on HTTP 403 — insufficient permissions."""

    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(403, message)


class DocsNotFoundError(DocsAPIError):
    """Raised on HTTP 404 — resource not found."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(404, message)


class DocsValidationError(DocsAPIError):
    """Raised on HTTP 422 — invalid request data."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(422, message)


class DocsRateLimitError(DocsAPIError):
    """Raised on HTTP 429 — rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(429, message)
