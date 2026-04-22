"""Configuration management using Pydantic Settings."""

import json
import os
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcp_docs.paths import session_file_path


class DocsConfig(BaseSettings):
    """Docs MCP server configuration, loaded from DOCS_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="DOCS_")

    base_url: str = "https://docs.numerique.gouv.fr"
    auth_mode: Literal["session", "oidc"] = "session"
    session_cookie: str | None = None
    session_file: Path | None = None
    oidc_token: str | None = None
    max_retries: int = Field(default=3, ge=0)
    max_concurrent: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def check_credentials(self) -> Self:
        """Ensure the required credential is present for the chosen auth mode."""
        if self.auth_mode == "session" and not self.session_cookie:
            raise ValueError(
                "DOCS_SESSION_COOKIE is required when auth_mode is 'session' "
                "(or write the cookie to DOCS_SESSION_FILE / run mcp-docs-refresh-session)"
            )
        if self.auth_mode == "oidc" and not self.oidc_token:
            raise ValueError("DOCS_OIDC_TOKEN is required when auth_mode is 'oidc'")
        return self


class SessionFileError(ValueError):
    """Raised when the session cookie file exists but cannot be used."""


def read_session_file(path: Path) -> str:
    """Read and validate the cookie value from a session JSON file.

    The file must be JSON with a non-empty ``cookie`` string. Any other shape
    raises ``SessionFileError`` with an actionable hint.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise SessionFileError(
            f"Session file not found at {path}. Run mcp-docs-refresh-session to create it."
        ) from e
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SessionFileError(
            f"Session file at {path} is not valid JSON. Run mcp-docs-refresh-session to regenerate it."
        ) from e
    if not isinstance(payload, dict):
        raise SessionFileError(f"Session file at {path} must contain a JSON object.")
    cookie = payload.get("cookie")
    if not isinstance(cookie, str) or not cookie:
        raise SessionFileError(f"Session file at {path} is missing a non-empty 'cookie' string.")
    return cookie


def _resolve_session_file() -> Path:
    """Return the user-chosen session file path, or the XDG default."""
    env_value = os.environ.get("DOCS_SESSION_FILE")
    return Path(env_value) if env_value else session_file_path()


def load_config() -> DocsConfig:
    """Build a DocsConfig, falling back to the session file when the cookie env is unset.

    Precedence for session-mode auth:
      1. ``DOCS_SESSION_COOKIE`` env var (explicit value wins).
      2. JSON at ``DOCS_SESSION_FILE`` or the XDG default path.
    Anything else (missing file, malformed file) surfaces a clear error.
    """
    auth_mode = os.environ.get("DOCS_AUTH_MODE", "session")
    if auth_mode == "session" and not os.environ.get("DOCS_SESSION_COOKIE"):
        candidate = _resolve_session_file()
        if candidate.exists():
            return DocsConfig(session_cookie=read_session_file(candidate))
    return DocsConfig()
