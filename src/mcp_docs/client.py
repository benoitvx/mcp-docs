"""HTTP client for the Docs API (La Suite numérique)."""

import os

import httpx

_API_PREFIX = "/api/v1.0"


class DocsClient:
    """Async HTTP client wrapping the Docs REST API."""

    def __init__(
        self,
        base_url: str,
        auth_mode: str,
        session_cookie: str | None = None,
        oidc_token: str | None = None,
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
        resp = await self._client.get(f"{_API_PREFIX}/documents/", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_document_content(
        self,
        document_id: str,
        content_format: str = "markdown",
    ) -> dict:
        """Retrieve document content in the specified format."""
        resp = await self._client.get(
            f"{_API_PREFIX}/documents/{document_id}/content/",
            params={"content_format": content_format},
        )
        resp.raise_for_status()
        return resp.json()

    async def create_document(
        self,
        markdown_content: str,
        title: str | None = None,
    ) -> dict:
        """Create a new document from markdown content (multipart upload)."""
        files = {"file": ("document.md", markdown_content.encode("utf-8"), "text/markdown")}
        data: dict[str, str] = {}
        if title:
            data["title"] = title
        resp = await self._client.post(f"{_API_PREFIX}/documents/", files=files, data=data)
        resp.raise_for_status()
        return resp.json()

    async def search_documents(
        self,
        query: str,
        page_size: int = 20,
    ) -> dict:
        """Search documents by title or content."""
        params: dict[str, str | int] = {"q": query, "page_size": page_size}
        resp = await self._client.get(f"{_API_PREFIX}/documents/", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_me(self) -> dict:
        """Get information about the authenticated user."""
        resp = await self._client.get(f"{_API_PREFIX}/users/me/")
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def create_client_from_env() -> DocsClient:
    """Create a DocsClient from environment variables."""
    base_url = os.environ.get("DOCS_BASE_URL", "https://docs.numerique.gouv.fr")
    auth_mode = os.environ.get("DOCS_AUTH_MODE", "session")
    session_cookie = os.environ.get("DOCS_SESSION_COOKIE")
    oidc_token = os.environ.get("DOCS_OIDC_TOKEN")

    return DocsClient(
        base_url=base_url,
        auth_mode=auth_mode,
        session_cookie=session_cookie,
        oidc_token=oidc_token,
    )
