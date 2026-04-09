"""Unit tests for DocsClient."""

import pytest
import respx
from httpx import Response

from mcp_docs.client import DocsClient, create_client_from_env

from .conftest import (
    BASE_URL,
    SAMPLE_CONTENT,
    SAMPLE_CREATED,
    SAMPLE_DOCUMENTS,
    SAMPLE_USER,
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
        with pytest.raises(ValueError, match="DOCS_SESSION_COOKIE"):
            DocsClient(base_url=BASE_URL, auth_mode="session")

    def test_missing_oidc_token_raises(self) -> None:
        with pytest.raises(ValueError, match="DOCS_OIDC_TOKEN"):
            DocsClient(base_url=BASE_URL, auth_mode="oidc")

    def test_unknown_auth_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown auth_mode"):
            DocsClient(base_url=BASE_URL, auth_mode="magic")


# --- list_documents ---


class TestListDocuments:
    @respx.mock
    async def test_list_documents(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/documents/").mock(return_value=Response(200, json=SAMPLE_DOCUMENTS))
        result = await docs_client_session.list_documents()
        assert result["count"] == 2
        assert len(result["results"]) == 2
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
        with pytest.raises(Exception):
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
        assert result["content"] == "Hello **world**"
        assert route.calls[0].request.url.params["content_format"] == "markdown"

    @respx.mock
    async def test_get_content_404(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/documents/nonexistent/content/").mock(return_value=Response(404))
        with pytest.raises(Exception):
            await docs_client_session.get_document_content("nonexistent")


# --- create_document ---


class TestCreateDocument:
    @respx.mock
    async def test_create_document(self, docs_client_session: DocsClient) -> None:
        route = respx.post(f"{API}/documents/").mock(return_value=Response(201, json=SAMPLE_CREATED))
        result = await docs_client_session.create_document("# Hello", title="New Document")
        assert result["id"] == "aaaa-bbbb-cccc-9999"
        assert route.called
        assert "X-CSRFToken" in route.calls[0].request.headers
        assert len(route.calls[0].request.headers["X-CSRFToken"]) == 64
        assert "Referer" in route.calls[0].request.headers

    @respx.mock
    async def test_create_document_without_title(self, docs_client_session: DocsClient) -> None:
        respx.post(f"{API}/documents/").mock(return_value=Response(201, json=SAMPLE_CREATED))
        result = await docs_client_session.create_document("# Hello")
        assert result["id"] == "aaaa-bbbb-cccc-9999"


# --- search_documents ---


class TestSearchDocuments:
    @respx.mock
    async def test_search(self, docs_client_session: DocsClient) -> None:
        route = respx.get(f"{API}/documents/").mock(return_value=Response(200, json=SAMPLE_DOCUMENTS))
        result = await docs_client_session.search_documents("test")
        assert result["count"] == 2
        assert route.calls[0].request.url.params["q"] == "test"


# --- get_me ---


class TestGetMe:
    @respx.mock
    async def test_get_me(self, docs_client_session: DocsClient) -> None:
        respx.get(f"{API}/users/me/").mock(return_value=Response(200, json=SAMPLE_USER))
        result = await docs_client_session.get_me()
        assert result["email"] == "user@example.gouv.fr"


# --- create_client_from_env ---


class TestFactory:
    def test_create_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCS_BASE_URL", "https://custom.local")
        monkeypatch.setenv("DOCS_AUTH_MODE", "session")
        monkeypatch.setenv("DOCS_SESSION_COOKIE", "abc123")
        client = create_client_from_env()
        assert str(client._client.base_url) == "https://custom.local"

    def test_create_from_env_missing_cookie(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCS_AUTH_MODE", "session")
        monkeypatch.delenv("DOCS_SESSION_COOKIE", raising=False)
        with pytest.raises(ValueError):
            create_client_from_env()
