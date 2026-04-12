"""Tests for MCP tool functions."""

import json
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from mcp_docs.app import AppContext
from mcp_docs.client import DocsClient
from mcp_docs.tools import (
    docs_create_document,
    docs_get_document_content,
    docs_get_me,
    docs_list_children,
    docs_list_documents,
    docs_search_documents,
)

from .conftest import (
    BASE_URL,
    SAMPLE_CHILDREN,
    SAMPLE_CONTENT,
    SAMPLE_CREATED,
    SAMPLE_DOCUMENTS,
    SAMPLE_USER,
)

API = f"{BASE_URL}/api/v1.0"


@pytest.fixture
def docs_client() -> DocsClient:
    return DocsClient(base_url=BASE_URL, auth_mode="session", session_cookie="test")


@pytest.fixture
def ctx(docs_client: DocsClient) -> MagicMock:
    """Mock MCP Context with lifespan_context."""
    context = MagicMock()
    context.request_context.lifespan_context = AppContext(client=docs_client)
    return context


# --- docs_list_documents ---


class TestListDocumentsTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/").mock(return_value=Response(200, json=SAMPLE_DOCUMENTS))
        result = await docs_list_documents(ctx=ctx)
        data = json.loads(result)
        assert data["count"] == 2
        assert len(data["documents"]) == 2
        assert data["documents"][0]["id"] == "aaaa-bbbb-cccc-0001"

    @respx.mock
    async def test_auth_error(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/").mock(return_value=Response(401))
        result = await docs_list_documents(ctx=ctx)
        assert "Authentication failed" in result

    async def test_invalid_page(self, ctx: MagicMock) -> None:
        result = await docs_list_documents(ctx=ctx, page=0)
        assert "Error" in result

    async def test_invalid_page_size(self, ctx: MagicMock) -> None:
        result = await docs_list_documents(ctx=ctx, page_size=200)
        assert "Error" in result


# --- docs_get_document_content ---


class TestGetDocumentContentTool:
    @respx.mock
    async def test_markdown(self, ctx: MagicMock) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        respx.get(f"{API}/documents/{doc_id}/content/").mock(
            return_value=Response(200, json=SAMPLE_CONTENT)
        )
        result = await docs_get_document_content(ctx=ctx, document_id=doc_id)
        assert "# Document One" in result
        assert "Hello **world**" in result

    @respx.mock
    async def test_html_format(self, ctx: MagicMock) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        html_content = {**SAMPLE_CONTENT, "content": "<p>Hello</p>"}
        respx.get(f"{API}/documents/{doc_id}/content/").mock(
            return_value=Response(200, json=html_content)
        )
        result = await docs_get_document_content(ctx=ctx, document_id=doc_id, content_format="html")
        data = json.loads(result)
        assert data["content"] == "<p>Hello</p>"

    @respx.mock
    async def test_not_found(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/missing/content/").mock(return_value=Response(404))
        result = await docs_get_document_content(ctx=ctx, document_id="missing")
        assert "not found" in result.lower()

    async def test_empty_id(self, ctx: MagicMock) -> None:
        result = await docs_get_document_content(ctx=ctx, document_id="")
        assert "Error" in result

    async def test_invalid_format(self, ctx: MagicMock) -> None:
        result = await docs_get_document_content(ctx=ctx, document_id="abc", content_format="xml")
        assert "Error" in result


# --- docs_create_document ---


class TestCreateDocumentTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/").mock(return_value=Response(201, json=SAMPLE_CREATED))
        result = await docs_create_document(ctx=ctx, title="New Document", markdown_content="# Hello")
        data = json.loads(result)
        assert data["id"] == "aaaa-bbbb-cccc-9999"
        assert data["title"] == "New Document"

    @respx.mock
    async def test_forbidden(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/").mock(return_value=Response(403))
        result = await docs_create_document(ctx=ctx, title="Test", markdown_content="content")
        assert "Access denied" in result

    async def test_empty_title(self, ctx: MagicMock) -> None:
        result = await docs_create_document(ctx=ctx, title="", markdown_content="content")
        assert "Error" in result

    async def test_empty_content(self, ctx: MagicMock) -> None:
        result = await docs_create_document(ctx=ctx, title="Title", markdown_content="")
        assert "Error" in result


# --- docs_search_documents ---


class TestSearchDocumentsTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/").mock(return_value=Response(200, json=SAMPLE_DOCUMENTS))
        result = await docs_search_documents(ctx=ctx, query="test")
        data = json.loads(result)
        assert data["count"] == 2

    async def test_empty_query(self, ctx: MagicMock) -> None:
        result = await docs_search_documents(ctx=ctx, query="")
        assert "Error" in result

    async def test_invalid_page_size(self, ctx: MagicMock) -> None:
        result = await docs_search_documents(ctx=ctx, query="test", page_size=200)
        assert "Error" in result

    @respx.mock
    async def test_server_error(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/").mock(return_value=Response(500))
        result = await docs_search_documents(ctx=ctx, query="test")
        assert "Request failed (HTTP 500)" in result


# --- docs_get_me ---


class TestGetMeTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/users/me/").mock(return_value=Response(200, json=SAMPLE_USER))
        result = await docs_get_me(ctx=ctx)
        data = json.loads(result)
        assert data["email"] == "user@example.gouv.fr"

    @respx.mock
    async def test_unauthorized(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/users/me/").mock(return_value=Response(401))
        result = await docs_get_me(ctx=ctx)
        assert "Authentication failed" in result


# --- docs_list_children ---


class TestListChildrenTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        parent_id = "aaaa-bbbb-cccc-0001"
        respx.get(f"{API}/documents/{parent_id}/children/").mock(
            return_value=Response(200, json=SAMPLE_CHILDREN)
        )
        result = await docs_list_children(ctx=ctx, document_id=parent_id)
        data = json.loads(result)
        assert data["count"] == 1
        assert len(data["documents"]) == 1
        assert data["documents"][0]["id"] == "aaaa-bbbb-cccc-child-01"

    @respx.mock
    async def test_auth_error(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/some-id/children/").mock(return_value=Response(401))
        result = await docs_list_children(ctx=ctx, document_id="some-id")
        assert "Authentication failed" in result

    @respx.mock
    async def test_not_found(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/bad-id/children/").mock(return_value=Response(404))
        result = await docs_list_children(ctx=ctx, document_id="bad-id")
        assert "not found" in result.lower()

    async def test_empty_document_id(self, ctx: MagicMock) -> None:
        result = await docs_list_children(ctx=ctx, document_id="")
        assert "Error" in result

    async def test_invalid_page(self, ctx: MagicMock) -> None:
        result = await docs_list_children(ctx=ctx, document_id="some-id", page=0)
        assert "Error" in result

    async def test_invalid_page_size(self, ctx: MagicMock) -> None:
        result = await docs_list_children(ctx=ctx, document_id="some-id", page_size=200)
        assert "Error" in result
