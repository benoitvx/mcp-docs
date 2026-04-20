"""Tests for DocsConfig (Pydantic Settings)."""

import pytest
from pydantic import ValidationError

from mcp_docs.config import DocsConfig


class TestDocsConfig:
    def test_valid_session_config(self) -> None:
        config = DocsConfig(base_url="https://docs.local", auth_mode="session", session_cookie="abc")
        assert config.base_url == "https://docs.local"
        assert config.auth_mode == "session"
        assert config.session_cookie == "abc"

    def test_valid_oidc_config(self) -> None:
        config = DocsConfig(base_url="https://docs.local", auth_mode="oidc", oidc_token="tok")
        assert config.auth_mode == "oidc"
        assert config.oidc_token == "tok"

    def test_missing_session_cookie_raises(self) -> None:
        with pytest.raises(ValidationError, match="DOCS_SESSION_COOKIE"):
            DocsConfig(base_url="https://docs.local", auth_mode="session")

    def test_missing_oidc_token_raises(self) -> None:
        with pytest.raises(ValidationError, match="DOCS_OIDC_TOKEN"):
            DocsConfig(base_url="https://docs.local", auth_mode="oidc")

    def test_invalid_auth_mode_raises(self) -> None:
        with pytest.raises(ValidationError):
            DocsConfig(base_url="https://docs.local", auth_mode="magic", session_cookie="x")  # type: ignore[arg-type]

    def test_defaults(self) -> None:
        config = DocsConfig(auth_mode="session", session_cookie="x")
        assert config.base_url == "https://docs.numerique.gouv.fr"
        assert config.max_retries == 3
        assert config.max_concurrent == 5

    def test_max_retries_ge_zero(self) -> None:
        with pytest.raises(ValidationError):
            DocsConfig(auth_mode="session", session_cookie="x", max_retries=-1)

    def test_max_concurrent_ge_one(self) -> None:
        with pytest.raises(ValidationError):
            DocsConfig(auth_mode="session", session_cookie="x", max_concurrent=0)

    def test_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCS_BASE_URL", "https://env.local")
        monkeypatch.setenv("DOCS_AUTH_MODE", "session")
        monkeypatch.setenv("DOCS_SESSION_COOKIE", "env-cookie")
        monkeypatch.setenv("DOCS_MAX_RETRIES", "7")
        config = DocsConfig()
        assert config.base_url == "https://env.local"
        assert config.session_cookie == "env-cookie"
        assert config.max_retries == 7
