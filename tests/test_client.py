"""Unit tests for DocsClient."""

import asyncio

import httpx
import pytest
import respx
from httpx import Response

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig
from mcp_docs.exceptions import DocsAPIError, DocsAuthError, DocsNotFoundError, DocsRateLimitError

from .conftest import (
    BASE_URL,
    SAMPLE_CHILDREN,
    SAMPLE_CONTENT,
    SAMPLE_CREATED,
    SAMPLE_DOCUMENTS,
    SAMPLE_USER,
    make_config,
)

API = f"{BASE_URL}/api/v1.0"


# --- Auth ---


class TestAuth:
    def test_session_cookie_set(self, docs_client_session: DocsClient) -> None:
        cookies = docs_client_session._client.cookies
        assert cookies.get("docs_sessionid") == "test-session-id"

    def test_oidc_header_set(self, docs_client_oidc: DocsClient) -> None:
        assert docs_client_oidc._client.headers["Authorization"] == "Bearer test-oidc-token"

    def test_missing_session_cookie_raises(self) -> None:
        with pytest.raises(Exception, match="DOCS_SESSION_COOKIE"):
            DocsConfig(base_url=BASE_URL, auth_mode="session")

    def test_missing_oidc_token_raises(self) -> None:
        with pytest.raises(Exception, match="DOCS_OIDC_TOKEN"):
            DocsConfig(base_url=BASE_URL, auth_mode="oidc")

    def test_unknown_auth_mode_raises(self) -> None:
        with pytest.raises(Exception):
            DocsConfig(base_url=BASE_URL, auth_mode="magic", session_cookie="x")  # type: ignore[arg-type]


# --- list_documents ---


class TestListDocuments:
    @respx.mock
    async def test_list_documents(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/documents/").mock(return_value=Response(200, json=SAMPLE_DOCUMENTS))
        result = await docs_client_session.list_documents()
        assert result.count == 2
        assert len(result.results) == 2
        assert route.called
        assert route.calls[0].request.url.params["page_size"] == "20"
        assert route.calls[0].request.url.params["ordering"] == "-updated_at"

    @respx.mock
    async def test_list_documents_with_title_filter(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/documents/").mock(return_value=Response(200, json=SAMPLE_DOCUMENTS))
        await docs_client_session.list_documents(title="Doc")

    @respx.mock
    async def test_list_documents_error(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/documents/").mock(return_value=Response(500))
        with pytest.raises(DocsAPIError):
            await docs_client_session.list_documents()


# --- get_document_content ---


class TestGetDocumentContent:
    @respx.mock
    async def test_get_content_markdown(self, docs_client_session: DocsClient) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        route = respx.get(f"{API}/documents/{doc_id}/content/").mock(
            return_value=Response(200, json=SAMPLE_CONTENT)
        )
        result = await docs_client_session.get_document_content(doc_id)
        assert result.content == "Hello **world**"
        assert route.calls[0].request.url.params["content_format"] == "markdown"

    @respx.mock
    async def test_get_content_404(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/documents/nonexistent/content/").mock(return_value=Response(404))
        with pytest.raises(DocsNotFoundError):
            await docs_client_session.get_document_content("nonexistent")


# --- create_document ---


class TestCreateDocument:
    @respx.mock
    async def test_create_document(self, docs_client_session: DocsClient) -> None:
        route = respx.post(f"{API}/documents/").mock(return_value=Response(201, json=SAMPLE_CREATED))
        result = await docs_client_session.create_document("# Hello", title="New Document")
        assert result.id == "aaaa-bbbb-cccc-9999"
        assert route.called
        assert "X-CSRFToken" in route.calls[0].request.headers
        assert len(route.calls[0].request.headers["X-CSRFToken"]) == 64
        assert "Referer" in route.calls[0].request.headers

    @respx.mock
    async def test_create_document_filename_uses_title(self, docs_client_session: DocsClient) -> None:
        route = respx.post(f"{API}/documents/").mock(return_value=Response(201, json=SAMPLE_CREATED))
        await docs_client_session.create_document("# Hello", title="Mon rapport")
        body = route.calls[0].request.content.decode("utf-8")
        assert 'filename="Mon rapport.md"' in body

    @respx.mock
    async def test_create_document_without_title(self, docs_client_session: DocsClient) -> None:
        route = respx.post(f"{API}/documents/").mock(return_value=Response(201, json=SAMPLE_CREATED))
        result = await docs_client_session.create_document("# Hello")
        assert result.id == "aaaa-bbbb-cccc-9999"
        body = route.calls[0].request.content.decode("utf-8")
        assert 'filename="document.md"' in body


# --- search_documents ---


class TestUpdateDocumentContent:
    @respx.mock
    async def test_update_content_via_temp_doc(self, docs_client_session: DocsClient) -> None:
        """The client creates a temp doc to convert markdown to Yjs server-side."""
        target_id = "aaaa-bbbb-cccc-0001"
        temp_id = "temp-1234-5678"

        # Step 1: create temp doc (multipart POST on /documents/)
        create_route = respx.post(f"{API}/documents/").mock(
            return_value=Response(201, json={"id": temp_id, "title": "_mcp_temp_convert"})
        )
        # Step 2: GET temp doc → returns content base64
        get_temp_route = respx.get(f"{API}/documents/{temp_id}/").mock(
            return_value=Response(200, json={"id": temp_id, "content": "ZmFrZXl4cw=="})
        )
        # Step 3: PATCH target doc with that content
        patch_route = respx.patch(f"{API}/documents/{target_id}/").mock(
            return_value=Response(200, json={"id": target_id, "title": "Doc"})
        )
        # Step 4: DELETE temp doc
        delete_route = respx.delete(f"{API}/documents/{temp_id}/").mock(return_value=Response(204))

        result = await docs_client_session.update_document_content(target_id, "# hello")
        assert result.id == target_id
        assert create_route.called
        assert get_temp_route.called
        assert patch_route.called
        assert delete_route.called

        # PATCH body carries the content from the temp doc + websocket flag
        import json as _json

        payload = _json.loads(patch_route.calls[0].request.read())
        assert payload["content"] == "ZmFrZXl4cw=="
        assert payload["websocket"] is True

    @respx.mock
    async def test_update_content_target_not_found(self, docs_client_session: DocsClient) -> None:
        temp_id = "temp-x"
        respx.post(f"{API}/documents/").mock(
            return_value=Response(201, json={"id": temp_id, "title": "_mcp_temp_convert"})
        )
        respx.get(f"{API}/documents/{temp_id}/").mock(
            return_value=Response(200, json={"id": temp_id, "content": "ZmFrZQ=="})
        )
        respx.patch(f"{API}/documents/missing/").mock(return_value=Response(404))
        respx.delete(f"{API}/documents/{temp_id}/").mock(return_value=Response(204))

        with pytest.raises(DocsNotFoundError):
            await docs_client_session.update_document_content("missing", "x")

    @respx.mock
    async def test_temp_doc_cleaned_up_even_when_patch_fails(self, docs_client_session: DocsClient) -> None:
        temp_id = "temp-cleanup"
        respx.post(f"{API}/documents/").mock(
            return_value=Response(201, json={"id": temp_id, "title": "_mcp_temp_convert"})
        )
        respx.get(f"{API}/documents/{temp_id}/").mock(
            return_value=Response(200, json={"id": temp_id, "content": "ZmFrZQ=="})
        )
        respx.patch(f"{API}/documents/target/").mock(return_value=Response(500))
        delete_route = respx.delete(f"{API}/documents/{temp_id}/").mock(return_value=Response(204))

        with pytest.raises(DocsAPIError):
            await docs_client_session.update_document_content("target", "x")
        assert delete_route.called  # cleanup happened despite error

    @respx.mock
    async def test_empty_content_from_temp_raises(self, docs_client_session: DocsClient) -> None:
        temp_id = "temp-empty"
        respx.post(f"{API}/documents/").mock(
            return_value=Response(201, json={"id": temp_id, "title": "_mcp_temp_convert"})
        )
        respx.get(f"{API}/documents/{temp_id}/").mock(
            return_value=Response(200, json={"id": temp_id, "content": None})
        )
        respx.delete(f"{API}/documents/{temp_id}/").mock(return_value=Response(204))

        with pytest.raises(DocsAPIError):
            await docs_client_session.update_document_content("target", "x")


class TestDeleteDocument:
    @respx.mock
    async def test_delete(self, docs_client_session: DocsClient) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        route = respx.delete(f"{API}/documents/{doc_id}/").mock(return_value=Response(204))
        await docs_client_session.delete_document(doc_id)
        assert route.called
        assert "X-CSRFToken" in route.calls[0].request.headers

    @respx.mock
    async def test_delete_404(self, docs_client_session: DocsClient) -> None:
        respx.delete(f"{API}/documents/missing/").mock(return_value=Response(404))
        with pytest.raises(DocsNotFoundError):
            await docs_client_session.delete_document("missing")


class TestListAccesses:
    @respx.mock
    async def test_list_accesses_returns_list(self, docs_client_session: DocsClient) -> None:
        """The accesses endpoint returns a raw list, not a paginated response."""
        doc_id = "aaaa-bbbb-cccc-0001"
        raw_accesses = [
            {"id": "a1", "user": {"id": "u1", "email": "a@b.fr"}, "role": "owner", "team": ""},
            {"id": "a2", "user": {"id": "u2", "email": "c@d.fr"}, "role": "editor", "team": ""},
        ]
        respx.get(f"{API}/documents/{doc_id}/accesses/").mock(
            return_value=Response(200, json=raw_accesses)
        )
        accesses = await docs_client_session.list_accesses(doc_id)
        assert isinstance(accesses, list)
        assert len(accesses) == 2
        assert accesses[0].role == "owner"


class TestUpdateDocumentTitle:
    @respx.mock
    async def test_update_title(self, docs_client_session: DocsClient) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        updated = {"id": doc_id, "title": "New Title"}
        route = respx.patch(f"{API}/documents/{doc_id}/").mock(return_value=Response(200, json=updated))
        result = await docs_client_session.update_document_title(doc_id, "New Title")
        assert result.title == "New Title"
        assert route.called
        assert "X-CSRFToken" in route.calls[0].request.headers

    @respx.mock
    async def test_update_title_404(self, docs_client_session: DocsClient) -> None:
        respx.patch(f"{API}/documents/missing/").mock(return_value=Response(404))
        with pytest.raises(DocsNotFoundError):
            await docs_client_session.update_document_title("missing", "New")


class TestSearchDocuments:
    @respx.mock
    async def test_search(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/documents/").mock(return_value=Response(200, json=SAMPLE_DOCUMENTS))
        result = await docs_client_session.search_documents("test")
        assert result.count == 2
        assert route.calls[0].request.url.params["q"] == "test"


# --- get_me ---


class TestGetMe:
    @respx.mock
    async def test_get_me(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/users/me/").mock(return_value=Response(200, json=SAMPLE_USER))
        result = await docs_client_session.get_me()
        assert result.email == "user@example.gouv.fr"


# --- list_children ---


class TestListChildren:
    @respx.mock
    async def test_list_children(self, docs_client_session: DocsClient) -> None:
        parent_id = "aaaa-bbbb-cccc-0001"
        route = respx.get(f"{API}/documents/{parent_id}/children/").mock(
            return_value=Response(200, json=SAMPLE_CHILDREN)
        )
        result = await docs_client_session.list_children(parent_id)
        assert result.count == 1
        assert len(result.results) == 1
        assert route.called
        assert route.calls[0].request.url.params["page_size"] == "20"

    @respx.mock
    async def test_list_children_error(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/documents/bad-id/children/").mock(return_value=Response(404))
        with pytest.raises(DocsNotFoundError):
            await docs_client_session.list_children("bad-id")


# --- retry logic ---


class TestRetry:
    @respx.mock
    async def test_retry_on_502(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/users/me/").mock(
            side_effect=[Response(502), Response(200, json=SAMPLE_USER)]
        )
        result = await docs_client_session.get_me()
        assert result.email == "user@example.gouv.fr"
        assert route.call_count == 2

    @respx.mock
    async def test_retry_on_503(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/users/me/").mock(
            side_effect=[Response(503), Response(200, json=SAMPLE_USER)]
        )
        result = await docs_client_session.get_me()
        assert result.email == "user@example.gouv.fr"
        assert route.call_count == 2

    @respx.mock
    async def test_retry_on_429(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/users/me/").mock(
            side_effect=[Response(429), Response(200, json=SAMPLE_USER)]
        )
        result = await docs_client_session.get_me()
        assert result.email == "user@example.gouv.fr"
        assert route.call_count == 2

    @respx.mock
    async def test_retry_on_timeout(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/users/me/").mock(
            side_effect=[httpx.ReadTimeout("timeout"), Response(200, json=SAMPLE_USER)]
        )
        result = await docs_client_session.get_me()
        assert result.email == "user@example.gouv.fr"
        assert route.call_count == 2

    @respx.mock
    async def test_no_retry_on_non_retryable_exception(self, docs_client_session: DocsClient) -> None:
        """ValueError is not retryable — covers _is_retryable returning False."""
        respx.get(f"{API}/users/me/").mock(
            side_effect=[ValueError("unexpected"), Response(200, json=SAMPLE_USER)]
        )
        with pytest.raises(ValueError):
            await docs_client_session.get_me()

    @respx.mock
    async def test_no_retry_on_404(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/documents/bad-id/content/").mock(return_value=Response(404))
        with pytest.raises(DocsNotFoundError):
            await docs_client_session.get_document_content("bad-id")
        assert route.call_count == 1

    @respx.mock
    async def test_max_retries_exhausted(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/users/me/").mock(
            side_effect=[Response(503), Response(503), Response(503), Response(503)]
        )
        with pytest.raises(DocsAPIError):
            await docs_client_session.get_me()

    @respx.mock
    async def test_retry_disabled(self) -> None:
        client = DocsClient(make_config(max_retries=0))
        route = respx.get(f"{API}/users/me/").mock(return_value=Response(502))
        with pytest.raises(DocsAPIError):
            await client.get_me()
        assert route.call_count == 1

    @respx.mock
    async def test_post_no_retry(self, docs_client_session: DocsClient) -> None:
        route = respx.post(f"{API}/documents/").mock(return_value=Response(502))
        with pytest.raises(DocsAPIError):
            await docs_client_session.create_document("# Test", title="Test")
        assert route.call_count == 1


# --- rate limiting ---


class TestRateLimiting:
    @respx.mock
    async def test_concurrent_requests_limited(self) -> None:
        client = DocsClient(make_config(max_concurrent=2))
        peak_concurrent = 0
        current_concurrent = 0

        async def slow_response(request: httpx.Request) -> Response:
            nonlocal peak_concurrent, current_concurrent
            current_concurrent += 1
            peak_concurrent = max(peak_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            current_concurrent -= 1
            return Response(200, json=SAMPLE_USER)

        respx.get(f"{API}/users/me/").mock(side_effect=slow_response)
        await asyncio.gather(*[client.get_me() for _ in range(5)])
        assert peak_concurrent <= 2

    @respx.mock
    async def test_semaphore_released_on_error(self) -> None:
        client = DocsClient(make_config(max_concurrent=1, max_retries=0))
        respx.get(f"{API}/users/me/").mock(
            side_effect=[Response(404), Response(200, json=SAMPLE_USER)]
        )
        with pytest.raises(DocsNotFoundError):
            await client.get_me()
        # Semaphore should be released — next call should succeed
        result = await client.get_me()
        assert result.email == "user@example.gouv.fr"


# --- config-based factory ---


class TestConfigFactory:
    def test_create_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCS_BASE_URL", "https://custom.local")
        monkeypatch.setenv("DOCS_AUTH_MODE", "session")
        monkeypatch.setenv("DOCS_SESSION_COOKIE", "abc123")
        config = DocsConfig()
        client = DocsClient(config)
        assert str(client._client.base_url) == "https://custom.local"

    def test_create_from_env_with_retry_and_concurrency(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCS_AUTH_MODE", "session")
        monkeypatch.setenv("DOCS_SESSION_COOKIE", "abc123")
        monkeypatch.setenv("DOCS_MAX_RETRIES", "5")
        monkeypatch.setenv("DOCS_MAX_CONCURRENT", "10")
        config = DocsConfig()
        client = DocsClient(config)
        assert client._max_retries == 5
        assert client._semaphore._value == 10

    async def test_close(self, docs_client_session: DocsClient) -> None:
        await docs_client_session.close()
        assert docs_client_session._client.is_closed

    def test_missing_cookie_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCS_AUTH_MODE", "session")
        monkeypatch.delenv("DOCS_SESSION_COOKIE", raising=False)
        with pytest.raises(Exception):
            DocsConfig()


# --- exception mapping ---


class TestExceptionMapping:
    @respx.mock
    async def test_401_raises_auth_error(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/users/me/").mock(return_value=Response(401))
        with pytest.raises(DocsAuthError):
            await docs_client_session.get_me()

    @respx.mock
    async def test_403_raises_permission_error(self, docs_client_session: DocsClient) -> None:
        from mcp_docs.exceptions import DocsPermissionError

        respx.get(f"{API}/users/me/").mock(return_value=Response(403))
        with pytest.raises(DocsPermissionError):
            await docs_client_session.get_me()

    @respx.mock
    async def test_404_raises_not_found_error(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/documents/bad/content/").mock(return_value=Response(404))
        with pytest.raises(DocsNotFoundError):
            await docs_client_session.get_document_content("bad")

    @respx.mock
    async def test_429_raises_rate_limit_error(self, docs_client_session: DocsClient) -> None:
        # 429 is retryable, so we need max_retries=0 to see the exception immediately
        client = DocsClient(make_config(max_retries=0))
        respx.get(f"{API}/users/me/").mock(return_value=Response(429))
        with pytest.raises(DocsRateLimitError):
            await client.get_me()

    @respx.mock
    async def test_500_raises_base_api_error(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/users/me/").mock(return_value=Response(500))
        with pytest.raises(DocsAPIError):
            await docs_client_session.get_me()
