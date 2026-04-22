"""CLI that refreshes the Docs session cookie by driving a browser via Playwright."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig, read_session_file
from mcp_docs.exceptions import DocsAPIError
from mcp_docs.paths import browser_profile_path, session_file_path

_PLAYWRIGHT_INSTALL_HINT = (
    "Playwright is required for mcp-docs-refresh-session. Install it with:\n"
    "  uv sync --extra browser\n"
    "  uv run playwright install chromium"
)


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def _session_file() -> Path:
    env = os.environ.get("DOCS_SESSION_FILE")
    return Path(env) if env else session_file_path()


def _base_url() -> str:
    return os.environ.get("DOCS_BASE_URL", "https://docs.numerique.gouv.fr")


async def _silent_probe(file: Path) -> bool:
    """Return True if the cookie in ``file`` still authenticates against /users/me/."""
    if not file.exists():
        return False
    try:
        cookie = read_session_file(file)
    except ValueError as e:
        _stderr(f"Warning: {e}")
        return False
    try:
        config = DocsConfig(session_cookie=cookie)
    except Exception as e:
        _stderr(f"Warning: existing cookie did not pass config validation ({e}).")
        return False
    client = DocsClient(config)
    try:
        await client.get_me()
        return True
    except DocsAPIError:
        return False
    finally:
        await client.close()


def _write_session_file(file: Path, cookie: str) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(file.parent, 0o700)
    payload = {
        "cookie": cookie,
        "obtained_at": datetime.now(tz=UTC).isoformat(),
        "source": "playwright-refresh",
    }
    tmp = file.with_suffix(file.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(file)


async def _wait_for_authenticated(page: object, probe_url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            resp = await page.request.get(probe_url)  # pyright: ignore[reportAttributeAccessIssue]
            if resp.status == 200:
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise SystemExit(
        f"Timed out after {int(timeout_s)}s waiting for authenticated session. "
        "Finish ProConnect login and re-run, or increase --timeout."
    )


async def _refresh_via_playwright(timeout_s: float, headless: bool) -> str:
    try:
        from playwright.async_api import async_playwright  # pyright: ignore[reportMissingImports]
    except ImportError as e:
        _stderr(_PLAYWRIGHT_INSTALL_HINT)
        raise SystemExit(2) from e

    base_url = _base_url().rstrip("/")
    profile_dir = browser_profile_path()
    profile_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(profile_dir, 0o700)

    _stderr(f"Launching Chromium (headless={headless}) with persistent profile at {profile_dir}")
    if not headless:
        _stderr(f"Navigating to {base_url} — complete ProConnect login in the browser window if prompted.")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
        )
        try:
            page = await context.new_page()
            await page.goto(f"{base_url}/")
            await _wait_for_authenticated(page, f"{base_url}/api/v1.0/users/me/", timeout_s)
            for c in await context.cookies():
                if c.get("name") == "docs_sessionid":
                    return c["value"]
            raise SystemExit("Authenticated but no docs_sessionid cookie was found in the browser context.")
        finally:
            await context.close()


def _notify_macos(body: str) -> None:
    """Best-effort macOS notification. Silent on other platforms or on failure."""
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{body}" with title "mcp-docs"'],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


async def _run(timeout_s: float, headless: bool) -> int:
    file = _session_file()
    _stderr(f"Session file: {file}")
    if await _silent_probe(file):
        _stderr("Session still valid — no refresh needed.")
        return 0
    cookie = await _refresh_via_playwright(timeout_s, headless)
    _write_session_file(file, cookie)
    _stderr(f"Session written to {file}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-docs-refresh-session",
        description="Refresh the Docs session cookie via a Playwright-driven browser.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Seconds to wait for ProConnect login to complete (default: 300).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium headless. Intended for scheduled unattended runs; "
        "exits non-zero and sends a macOS notification if ProConnect re-authentication is required.",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.timeout, args.headless))
    except SystemExit as e:
        if args.headless and e.code not in (0, None):
            _notify_macos("Session refresh failed. Run mcp-docs-refresh-session manually.")
        raise


if __name__ == "__main__":
    main()
