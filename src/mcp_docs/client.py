"""HTTP client for the Docs API (La Suite numérique)."""

import asyncio
import logging
import secrets
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from mcp_docs.config import DocsConfig
from mcp_docs.exceptions import (
    DocsAPIError,
    DocsAuthError,
    DocsNotFoundError,
    DocsPermissionError,
    DocsRateLimitError,
    DocsValidationError,
)
from mcp_docs.models import DocumentAccess, DocumentContent, DocumentSummary, Invitation, PaginatedResponse, UserInfo

_API_PREFIX = "/api/v1.0"

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[int, type[DocsAPIError]] = {
    401: DocsAuthError,
    403: DocsPermissionError,
    404: DocsNotFoundError,
    422: DocsValidationError,
    429: DocsRateLimitError,
}


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors that should be retried."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, DocsRateLimitError):
        return True
    if isinstance(exc, DocsAPIError):
        return exc.status_code in (502, 503)
    return False


def _raise_for_api_status(resp: httpx.Response) -> None:
    """Raise a typed DocsAPIError if the response indicates an error."""
    if resp.is_success:
        return
    status = resp.status_code
    exc_cls = _STATUS_MAP.get(status, DocsAPIError)
    if exc_cls is DocsAPIError:
        raise DocsAPIError(status, f"API request failed (HTTP {status})")
    raise exc_cls()  # pyright: ignore[reportCallIssue]  # subclasses define default message


class DocsClient:
    """Async HTTP client wrapping the Docs REST API."""

    def __init__(self, config: DocsConfig) -> None:
        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}

        if config.auth_mode == "session":
            assert config.session_cookie  # guaranteed by DocsConfig validator
            cookies["docs_sessionid"] = config.session_cookie
        else:
            assert config.oidc_token  # guaranteed by DocsConfig validator
            headers["Authorization"] = f"Bearer {config.oidc_token}"

        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers=headers,
            cookies=httpx.Cookies(cookies),
            timeout=30.0,
        )
        self._max_retries = config.max_retries
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

    async def _get(self, url: str, **kwargs: Any) -> Any:
        """Execute a GET request with retry and concurrency limiting.

        Returns parsed JSON (may be dict or list depending on endpoint).
        """
        async with self._semaphore:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_is_retryable),
                stop=stop_after_attempt(max(1, self._max_retries + 1)),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                reraise=True,
            ):
                with attempt:
                    resp = await self._client.get(url, **kwargs)
                    _raise_for_api_status(resp)
                    return resp.json()
        raise RuntimeError("Unreachable")  # pragma: no cover

    async def _post(self, url: str, **kwargs: Any) -> Any:
        """Execute a POST request with concurrency limiting (no retry)."""
        async with self._semaphore:
            resp = await self._client.post(url, **kwargs)
            _raise_for_api_status(resp)
            return resp.json()

    async def _patch(self, url: str, **kwargs: Any) -> Any:
        """Execute a PATCH request with concurrency limiting (no retry)."""
        async with self._semaphore:
            resp = await self._client.patch(url, **kwargs)
            _raise_for_api_status(resp)
            return resp.json()

    async def _put(self, url: str, **kwargs: Any) -> Any:
        """Execute a PUT request with concurrency limiting (no retry)."""
        async with self._semaphore:
            resp = await self._client.put(url, **kwargs)
            _raise_for_api_status(resp)
            return resp.json()

    async def _delete(self, url: str, **kwargs: Any) -> None:
        """Execute a DELETE request with concurrency limiting (no retry)."""
        async with self._semaphore:
            resp = await self._client.delete(url, **kwargs)
            _raise_for_api_status(resp)

    # --- Document operations ---

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 20,
        ordering: str = "-updated_at",
        title: str | None = None,
    ) -> PaginatedResponse[DocumentSummary]:
        """List documents, paginated and ordered."""
        params: dict[str, str | int] = {
            "page": page,
            "page_size": page_size,
            "ordering": ordering,
        }
        if title:
            params["title"] = title
        data = await self._get(f"{_API_PREFIX}/documents/", params=params)
        return PaginatedResponse[DocumentSummary].model_validate(data)

    async def get_document_content(
        self,
        document_id: str,
        content_format: str = "markdown",
    ) -> DocumentContent:
        """Retrieve document content in the specified format."""
        data = await self._get(
            f"{_API_PREFIX}/documents/{document_id}/content/",
            params={"content_format": content_format},
        )
        return DocumentContent.model_validate(data)

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
    ) -> DocumentSummary:
        """Create a new document from markdown content (multipart upload)."""
        filename = f"{title}.md" if title else "document.md"
        files = {"file": (filename, markdown_content.encode("utf-8"), "text/markdown")}
        data_fields: dict[str, str] = {}
        if title:
            data_fields["title"] = title
        raw = await self._post(
            f"{_API_PREFIX}/documents/",
            files=files,
            data=data_fields,
            headers=self._make_csrf_headers(),
        )
        return DocumentSummary.model_validate(raw)

    async def update_document_title(
        self,
        document_id: str,
        title: str,
    ) -> DocumentSummary:
        """Update a document's title (PATCH JSON)."""
        raw = await self._patch(
            f"{_API_PREFIX}/documents/{document_id}/",
            json={"title": title},
            headers=self._make_csrf_headers(),
        )
        return DocumentSummary.model_validate(raw)

    async def _markdown_to_yjs_base64(self, markdown: str) -> str:
        """Convert markdown to base64-encoded Yjs via the backend's own converter.

        The backend runs a Y-Provider service that converts markdown to the
        BlockNote/Yjs format on document creation. We exploit this by creating
        a temporary document with the markdown, copying its generated content,
        then deleting the temp document.
        """
        temp = await self.create_document(markdown, title="_mcp_temp_convert")
        temp_id = temp.id
        try:
            data = await self._get(f"{_API_PREFIX}/documents/{temp_id}/")
            content = data.get("content")
            if not content:
                raise DocsAPIError(500, "Temp doc returned empty content field")
            return content
        finally:
            try:
                await self.delete_document(temp_id)
            except DocsAPIError:
                pass  # best-effort cleanup

    async def update_document_content(
        self,
        document_id: str,
        content: str,
    ) -> DocumentSummary:
        """Replace a document's content with markdown.

        Markdown formatting is preserved (headings, bold, italic, lists, etc.)
        via the backend's Y-Provider conversion service.
        """
        yjs_b64 = await self._markdown_to_yjs_base64(content)
        raw = await self._patch(
            f"{_API_PREFIX}/documents/{document_id}/",
            json={"content": yjs_b64, "websocket": True},
            headers=self._make_csrf_headers(),
        )
        return DocumentSummary.model_validate(raw)

    async def search_documents(
        self,
        query: str,
        page_size: int = 20,
    ) -> PaginatedResponse[DocumentSummary]:
        """Search documents by title or content."""
        params: dict[str, str | int] = {"q": query, "page_size": page_size}
        data = await self._get(f"{_API_PREFIX}/documents/", params=params)
        return PaginatedResponse[DocumentSummary].model_validate(data)

    async def get_me(self) -> UserInfo:
        """Get information about the authenticated user."""
        data = await self._get(f"{_API_PREFIX}/users/me/")
        return UserInfo.model_validate(data)

    async def list_children(
        self,
        document_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[DocumentSummary]:
        """List child documents of a given parent document."""
        params: dict[str, str | int] = {"page": page, "page_size": page_size}
        data = await self._get(
            f"{_API_PREFIX}/documents/{document_id}/children/",
            params=params,
        )
        return PaginatedResponse[DocumentSummary].model_validate(data)

    async def get_document(self, document_id: str) -> DocumentSummary:
        """Fetch a document's metadata (including creator)."""
        data = await self._get(f"{_API_PREFIX}/documents/{document_id}/")
        return DocumentSummary.model_validate(data)

    async def delete_document(self, document_id: str) -> None:
        """Delete a document (soft delete, moved to trashbin)."""
        await self._delete(
            f"{_API_PREFIX}/documents/{document_id}/",
            headers=self._make_csrf_headers(),
        )

    # --- Access management ---

    async def list_accesses(self, document_id: str) -> list[DocumentAccess]:
        """List all access entries for a document.

        The API returns a raw (non-paginated) list.
        """
        data = await self._get(f"{_API_PREFIX}/documents/{document_id}/accesses/")
        return [DocumentAccess.model_validate(item) for item in data]

    async def grant_access(
        self,
        document_id: str,
        user_id: str,
        role: str,
    ) -> DocumentAccess:
        """Grant a user access to a document."""
        raw = await self._post(
            f"{_API_PREFIX}/documents/{document_id}/accesses/",
            json={"user": user_id, "role": role},
            headers=self._make_csrf_headers(),
        )
        return DocumentAccess.model_validate(raw)

    async def update_access(
        self,
        document_id: str,
        access_id: str,
        role: str,
    ) -> DocumentAccess:
        """Update the role of an existing access entry."""
        raw = await self._patch(
            f"{_API_PREFIX}/documents/{document_id}/accesses/{access_id}/",
            json={"role": role},
            headers=self._make_csrf_headers(),
        )
        return DocumentAccess.model_validate(raw)

    async def revoke_access(
        self,
        document_id: str,
        access_id: str,
    ) -> None:
        """Revoke a user's access to a document."""
        await self._delete(
            f"{_API_PREFIX}/documents/{document_id}/accesses/{access_id}/",
            headers=self._make_csrf_headers(),
        )

    # --- Invitation management ---

    async def list_invitations(
        self,
        document_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[Invitation]:
        """List pending invitations for a document."""
        params: dict[str, str | int] = {"page": page, "page_size": page_size}
        data = await self._get(
            f"{_API_PREFIX}/documents/{document_id}/invitations/",
            params=params,
        )
        return PaginatedResponse[Invitation].model_validate(data)

    async def create_invitation(
        self,
        document_id: str,
        email: str,
        role: str,
    ) -> Invitation:
        """Send an invitation to access a document."""
        raw = await self._post(
            f"{_API_PREFIX}/documents/{document_id}/invitations/",
            json={"email": email, "role": role},
            headers=self._make_csrf_headers(),
        )
        return Invitation.model_validate(raw)

    # --- AI operations ---

    async def ai_transform(self, document_id: str, text: str, action: str) -> str:
        """Apply an AI transformation to text, scoped to a document."""
        raw = await self._post(
            f"{_API_PREFIX}/documents/{document_id}/ai-transform/",
            json={"text": text, "action": action},
            headers=self._make_csrf_headers(),
        )
        return raw["answer"] if "answer" in raw else raw.get("transformed_text", "")

    async def ai_translate(self, document_id: str, text: str, language: str) -> str:
        """Translate text into the given language, scoped to a document."""
        raw = await self._post(
            f"{_API_PREFIX}/documents/{document_id}/ai-translate/",
            json={"text": text, "language": language},
            headers=self._make_csrf_headers(),
        )
        return raw["answer"] if "answer" in raw else raw.get("translated_text", "")

    # --- Link configuration ---

    async def update_link_configuration(
        self,
        document_id: str,
        link_reach: str,
        link_role: str | None,
    ) -> dict:
        """Configure the share-link reach and role for a document."""
        payload: dict[str, str | None] = {"link_reach": link_reach, "link_role": link_role}
        raw = await self._put(
            f"{_API_PREFIX}/documents/{document_id}/link-configuration/",
            json=payload,
            headers=self._make_csrf_headers(),
        )
        return raw  # type: ignore[no-any-return]

    # --- Favorites ---

    async def list_favorites(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[DocumentSummary]:
        """List the user's favorite documents."""
        params: dict[str, str | int] = {"page": page, "page_size": page_size}
        data = await self._get(f"{_API_PREFIX}/documents/favorite_list/", params=params)
        return PaginatedResponse[DocumentSummary].model_validate(data)

    async def add_favorite(self, document_id: str) -> None:
        """Mark a document as favorite."""
        await self._post(
            f"{_API_PREFIX}/documents/{document_id}/favorite/",
            headers=self._make_csrf_headers(),
        )

    async def remove_favorite(self, document_id: str) -> None:
        """Remove a document from favorites."""
        await self._delete(
            f"{_API_PREFIX}/documents/{document_id}/favorite/",
            headers=self._make_csrf_headers(),
        )

    # --- Trashbin & restore ---

    async def list_trashbin(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[DocumentSummary]:
        """List documents in the trashbin (soft-deleted, within retention)."""
        params: dict[str, str | int] = {"page": page, "page_size": page_size}
        data = await self._get(f"{_API_PREFIX}/documents/trashbin/", params=params)
        return PaginatedResponse[DocumentSummary].model_validate(data)

    async def restore_document(self, document_id: str) -> None:
        """Restore a soft-deleted document from the trashbin."""
        await self._post(
            f"{_API_PREFIX}/documents/{document_id}/restore/",
            headers=self._make_csrf_headers(),
        )

    # --- Move & duplicate ---

    async def move_document(
        self,
        document_id: str,
        target_document_id: str,
        position: str,
    ) -> dict:
        """Move a document in the hierarchy."""
        raw = await self._post(
            f"{_API_PREFIX}/documents/{document_id}/move/",
            json={"target_document_id": target_document_id, "position": position},
            headers=self._make_csrf_headers(),
        )
        return raw  # type: ignore[no-any-return]

    async def duplicate_document(
        self,
        document_id: str,
        with_descendants: bool = False,
        with_accesses: bool = False,
    ) -> dict:
        """Duplicate a document (optionally its subtree and access permissions)."""
        raw = await self._post(
            f"{_API_PREFIX}/documents/{document_id}/duplicate/",
            json={"with_descendants": with_descendants, "with_accesses": with_accesses},
            headers=self._make_csrf_headers(),
        )
        return raw  # type: ignore[no-any-return]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
