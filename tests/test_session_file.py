"""Tests for the session file loader and ``load_config`` precedence."""

import json
from pathlib import Path

import pytest

from mcp_docs.config import DocsConfig, SessionFileError, load_config, read_session_file


class TestReadSessionFile:
    def test_valid_file_returns_cookie(self, tmp_path: Path) -> None:
        file = tmp_path / "session.json"
        file.write_text(json.dumps({"cookie": "abc123", "obtained_at": "2026-04-22T10:00:00+00:00"}))
        assert read_session_file(file) == "abc123"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SessionFileError, match="not found"):
            read_session_file(tmp_path / "nope.json")

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        file = tmp_path / "session.json"
        file.write_text("{not json")
        with pytest.raises(SessionFileError, match="not valid JSON"):
            read_session_file(file)

    def test_non_object_payload_raises(self, tmp_path: Path) -> None:
        file = tmp_path / "session.json"
        file.write_text(json.dumps(["array", "not", "object"]))
        with pytest.raises(SessionFileError, match="JSON object"):
            read_session_file(file)

    def test_missing_cookie_key_raises(self, tmp_path: Path) -> None:
        file = tmp_path / "session.json"
        file.write_text(json.dumps({"obtained_at": "now"}))
        with pytest.raises(SessionFileError, match="non-empty 'cookie'"):
            read_session_file(file)

    def test_empty_cookie_raises(self, tmp_path: Path) -> None:
        file = tmp_path / "session.json"
        file.write_text(json.dumps({"cookie": ""}))
        with pytest.raises(SessionFileError, match="non-empty 'cookie'"):
            read_session_file(file)

    def test_non_string_cookie_raises(self, tmp_path: Path) -> None:
        file = tmp_path / "session.json"
        file.write_text(json.dumps({"cookie": 12345}))
        with pytest.raises(SessionFileError, match="non-empty 'cookie'"):
            read_session_file(file)


class TestLoadConfig:
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k in (
            "DOCS_BASE_URL",
            "DOCS_AUTH_MODE",
            "DOCS_SESSION_COOKIE",
            "DOCS_SESSION_FILE",
            "DOCS_OIDC_TOKEN",
        ):
            monkeypatch.delenv(k, raising=False)

    def test_env_cookie_takes_precedence_over_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clean_env(monkeypatch)
        file = tmp_path / "session.json"
        file.write_text(json.dumps({"cookie": "from-file"}))
        monkeypatch.setenv("DOCS_SESSION_COOKIE", "from-env")
        monkeypatch.setenv("DOCS_SESSION_FILE", str(file))
        config = load_config()
        assert config.session_cookie == "from-env"

    def test_file_is_used_when_env_cookie_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clean_env(monkeypatch)
        file = tmp_path / "session.json"
        file.write_text(json.dumps({"cookie": "from-file"}))
        monkeypatch.setenv("DOCS_SESSION_FILE", str(file))
        config = load_config()
        assert config.session_cookie == "from-file"

    def test_default_path_is_tried_when_no_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clean_env(monkeypatch)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        default_file = tmp_path / "mcp-docs" / "session.json"
        default_file.parent.mkdir(parents=True)
        default_file.write_text(json.dumps({"cookie": "from-default"}))
        config = load_config()
        assert config.session_cookie == "from-default"

    def test_missing_file_surfaces_helpful_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clean_env(monkeypatch)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))  # empty dir
        with pytest.raises(ValueError, match="DOCS_SESSION_COOKIE"):
            load_config()

    def test_malformed_file_surfaces_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clean_env(monkeypatch)
        file = tmp_path / "session.json"
        file.write_text("garbage")
        monkeypatch.setenv("DOCS_SESSION_FILE", str(file))
        with pytest.raises(SessionFileError):
            load_config()

    def test_oidc_mode_skips_file_lookup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clean_env(monkeypatch)
        monkeypatch.setenv("DOCS_AUTH_MODE", "oidc")
        monkeypatch.setenv("DOCS_OIDC_TOKEN", "tok")
        monkeypatch.setenv("DOCS_SESSION_FILE", str(tmp_path / "nonexistent.json"))
        config = load_config()
        assert config.auth_mode == "oidc"
        assert config.oidc_token == "tok"
        assert config.session_cookie is None

    def test_returned_instance_is_valid_docsconfig(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clean_env(monkeypatch)
        file = tmp_path / "session.json"
        file.write_text(json.dumps({"cookie": "c"}))
        monkeypatch.setenv("DOCS_SESSION_FILE", str(file))
        config = load_config()
        assert isinstance(config, DocsConfig)
        assert config.auth_mode == "session"
