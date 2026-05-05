"""XDG-style paths for user-level state and data files."""

import os
from pathlib import Path

_APP_NAME = "mcp-docs"


def _xdg_home(env_var: str, fallback: str) -> Path:
    value = os.environ.get(env_var)
    if value:
        return Path(value)
    return Path.home() / fallback


def session_file_path() -> Path:
    """Return the default path of the session cookie file.

    Follows XDG Base Directory: ``$XDG_STATE_HOME/mcp-docs/session.json`` with
    fallback to ``~/.local/state/mcp-docs/session.json``.
    """
    return _xdg_home("XDG_STATE_HOME", ".local/state") / _APP_NAME / "session.json"


def browser_profile_path() -> Path:
    """Return the default path of the persistent Chromium profile used by refresh.

    Follows XDG Base Directory: ``$XDG_DATA_HOME/mcp-docs/browser-profile`` with
    fallback to ``~/.local/share/mcp-docs/browser-profile``.
    """
    return _xdg_home("XDG_DATA_HOME", ".local/share") / _APP_NAME / "browser-profile"


def log_file_path() -> Path:
    """Return the default path of the server log file.

    Follows XDG Base Directory: ``$XDG_STATE_HOME/mcp-docs/server.log`` with
    fallback to ``~/.local/state/mcp-docs/server.log``.
    """
    return _xdg_home("XDG_STATE_HOME", ".local/state") / _APP_NAME / "server.log"
