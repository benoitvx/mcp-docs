"""Configuration management using Pydantic Settings."""

from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DocsConfig(BaseSettings):
    """Docs MCP server configuration, loaded from DOCS_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="DOCS_")

    base_url: str = "https://docs.numerique.gouv.fr"
    auth_mode: Literal["session", "oidc"] = "session"
    session_cookie: str | None = None
    oidc_token: str | None = None
    max_retries: int = Field(default=3, ge=0)
    max_concurrent: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def check_credentials(self) -> Self:
        """Ensure the required credential is present for the chosen auth mode."""
        if self.auth_mode == "session" and not self.session_cookie:
            raise ValueError("DOCS_SESSION_COOKIE is required when auth_mode is 'session'")
        if self.auth_mode == "oidc" and not self.oidc_token:
            raise ValueError("DOCS_OIDC_TOKEN is required when auth_mode is 'oidc'")
        return self
