"""HTTP client for the Docs API (La Suite numérique)."""

import asyncio
import logging
import os
import secrets
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

_API_PREFIX = "/api/v1.0"

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors that should be retried."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 502, 503)
    return False


class DocsClient:
    """Async HTTP client wrapping the Docs REST API."""

    def __init__(
        self,
        base_url: str,
        auth_mode: str,
        session_cookie: str | None = None,
        oidc_token: str | None = None,
        max_retries: int = 3,
        max_concurrent: int = 5,
    ) -> None:
        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}

        if auth_mode == "session":
            if not session_cookie:
                raise ValueError("DOCS_SESSION_COOKIE is required when auth_mode is 'session'")
            cookies["docs_sessionid"] = session_cookie
        elif auth_mode == "oidc":
            if not oidc_token:
                raise ValueError("DOCS_OIDC_TOKEN is required when auth_mode is 'oidc'")
            headers["Authorization"] = f"Bearer {oidc_token}"
        else:
            raise ValueError(f"Unknown auth_mode: {auth_mode!r}. Expected 'session' or 'oidc'.")

        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            cookies=httpx.Cookies(cookies),
            timeout=30.0,
        )
        self._max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _get(self, url: str, **kwargs: Any) -> dict:
        """Execute a GET request with retry and concurrency limiting."""
        async with self._semaphore:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_is_retryable),
                stop=stop_after_attempt(max(1, self._max_retries + 1)),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                reraise=True,
            ):
                with attempt:
                    resp = await self._client.get(url, **kwargs)
                    resp.raise_for_status()
                    return resp.json()  # type: ignore[no-any-return]
        raise RuntimeError("Unreachable")  # pragma: no cover

    async def _post(self, url: str, **kwargs: Any) -> dict:
        """Execute a POST request with concurrency limiting (no retry)."""
        async with self._semaphore:
            resp = await self._client.post(url, **kwargs)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 20,
        ordering: str = "-updated_at",
        title: str | None = None,
    ) -> dict:
        """List documents, paginated and ordered."""
        params: dict[str, str | int] = {
            "page": page,
            "page_size": page_size,
            "ordering": ordering,
        }
        if title:
            params["title"] = title
        return await self._get(f"{_API_PREFIX}/documents/", params=params)

    async def get_document_content(
        self,
        document_id: str,
        content_format: str = "markdown",
    ) -> dict:
        """Retrieve document content in the specified format."""
        return await self._get(
            f"{_API_PREFIX}/documents/{document_id}/content/",
            params={"content_format": content_format},
        )

    def _make_csrf_headers(self) -> dict[str, str]:
        """Generate CSRF cookie + header for POST requests.

        Django requires both a csrftoken cookie and a matching X-CSRFToken
        header. The token must be 64 characters long. We generate one and
        inject it into both the cookie jar and request headers.
        """
        csrf_token = secrets.token_hex(32)  # 64 hex chars
        self._client.cookies.set("csrftoken", csrf_token)
        return {
            "X-CSRFToken": csrf_token,
            "Referer": str(self._client.base_url),
        }

    async def create_document(
        self,
        markdown_content: str,
        title: str | None = None,
    ) -> dict:
        """Create a new document from markdown content (multipart upload)."""
        filename = f"{title}.md" if title else "document.md"
        files = {"file": (filename, markdown_content.encode("utf-8"), "text/markdown")}
        data: dict[str, str] = {}
        if title:
            data["title"] = title
        return await self._post(
            f"{_API_PREFIX}/documents/",
            files=files,
            data=data,
            headers=self._make_csrf_headers(),
        )

    async def search_documents(
        self,
        query: str,
        page_size: int = 20,
    ) -> dict:
        """Search documents by title or content."""
        params: dict[str, str | int] = {"q": query, "page_size": page_size}
        return await self._get(f"{_API_PREFIX}/documents/", params=params)

    async def get_me(self) -> dict:
        """Get information about the authenticated user."""
        return await self._get(f"{_API_PREFIX}/users/me/")

    async def list_children(
        self,
        document_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """List child documents of a given parent document."""
        params: dict[str, str | int] = {"page": page, "page_size": page_size}
        return await self._get(
            f"{_API_PREFIX}/documents/{document_id}/children/",
            params=params,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def create_client_from_env() -> DocsClient:
    """Create a DocsClient from environment variables."""
    base_url = os.environ.get("DOCS_BASE_URL", "https://docs.numerique.gouv.fr")
    auth_mode = os.environ.get("DOCS_AUTH_MODE", "session")
    session_cookie = os.environ.get("DOCS_SESSION_COOKIE")
    oidc_token = os.environ.get("DOCS_OIDC_TOKEN")
    max_retries = int(os.environ.get("DOCS_MAX_RETRIES", "3"))
    max_concurrent = int(os.environ.get("DOCS_MAX_CONCURRENT", "5"))

    return DocsClient(
        base_url=base_url,
        auth_mode=auth_mode,
        session_cookie=session_cookie,
        oidc_token=oidc_token,
        max_retries=max_retries,
        max_concurrent=max_concurrent,
    )
