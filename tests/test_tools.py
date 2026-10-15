"""Tests for MCP tool functions."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response

from mcp_docs.app import AppContext
from mcp_docs.client import DocsClient
from mcp_docs.tools import (
    docs_create_document,
    docs_delete_document,
    docs_get_document_content,
    docs_get_me,
    docs_list_children,
    docs_list_documents,
    docs_search_documents,
    docs_update_document_content,
    docs_update_document_title,
)

from .conftest import (
    BASE_URL,
    SAMPLE_CHILDREN,
    SAMPLE_CONTENT,
    SAMPLE_CREATED,
    SAMPLE_DOCUMENT_DETAIL,
    SAMPLE_DOCUMENT_DETAIL_OTHER_CREATOR,
    SAMPLE_DOCUMENTS,
    SAMPLE_USER,
    make_config,
    yhub_state,
)

API = f"{BASE_URL}/api/v1.0"


@pytest.fixture
def docs_client() -> DocsClient:
    return DocsClient(make_config())


@pytest.fixture
def ctx(docs_client: DocsClient) -> MagicMock:
    """Mock MCP Context with lifespan_context."""
    context = MagicMock()
    context.request_context.lifespan_context = AppContext(config=make_config(), client=docs_client)
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
        respx.get(f"{API}/documents/{doc_id}/formatted-content/").mock(
            return_value=Response(200, json=SAMPLE_CONTENT)
        )
        result = await docs_get_document_content(ctx=ctx, document_id=doc_id)
        assert "# Document One" in result
        assert "Hello **world**" in result

    @respx.mock
    async def test_html_format(self, ctx: MagicMock) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        html_content = {**SAMPLE_CONTENT, "content": "<p>Hello</p>"}
        respx.get(f"{API}/documents/{doc_id}/formatted-content/").mock(
            return_value=Response(200, json=html_content)
        )
        result = await docs_get_document_content(ctx=ctx, document_id=doc_id, content_format="html")
        data = json.loads(result)
        assert data["content"] == "<p>Hello</p>"

    @respx.mock
    async def test_not_found(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/missing/formatted-content/").mock(return_value=Response(404))
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

    @respx.mock
    async def test_both_content_and_file_path(self, ctx: MagicMock, tmp_path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# x")
        result = await docs_create_document(
            ctx=ctx, title="T", markdown_content="# x", file_path=str(f)
        )
        assert "Error" in result
        assert len(respx.calls) == 0

    @respx.mock
    async def test_neither_content_nor_file_path(self, ctx: MagicMock) -> None:
        result = await docs_create_document(ctx=ctx, title="T")
        assert "Error" in result
        assert len(respx.calls) == 0

    @respx.mock
    async def test_file_path_relative_refused(self, ctx: MagicMock, tmp_path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# x")
        result = await docs_create_document(ctx=ctx, title="T", file_path=f.name)
        assert "Error" in result
        assert len(respx.calls) == 0

    @respx.mock
    async def test_file_path_txt_extension_refused(self, ctx: MagicMock, tmp_path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("# x")
        result = await docs_create_document(ctx=ctx, title="T", file_path=str(f))
        assert "Error" in result
        assert "file_path" in result
        assert len(respx.calls) == 0

    @respx.mock
    async def test_file_path_symlink_to_txt_refused(self, ctx: MagicMock, tmp_path) -> None:
        txt = tmp_path / "secret.txt"
        txt.write_text("# x")
        link = tmp_path / "doc.md"
        link.symlink_to(txt)
        result = await docs_create_document(ctx=ctx, title="T", file_path=str(link))
        assert "Error" in result
        assert len(respx.calls) == 0

    @respx.mock
    async def test_file_path_too_large_refused(self, ctx: MagicMock, tmp_path) -> None:
        big = tmp_path / "big.md"
        big.write_bytes(b"x" * (5 * 1024 * 1024 + 10))
        result = await docs_create_document(ctx=ctx, title="T", file_path=str(big))
        assert "Error" in result
        assert len(respx.calls) == 0

    @respx.mock
    async def test_file_path_not_existing_refused(self, ctx: MagicMock, tmp_path) -> None:
        result = await docs_create_document(ctx=ctx, title="T", file_path=str(tmp_path / "nope.md"))
        assert "Error" in result
        assert len(respx.calls) == 0

    @respx.mock
    async def test_file_path_valid_sends_file_content(self, ctx: MagicMock, tmp_path) -> None:
        md = tmp_path / "doc.md"
        content = "# Titre du fichier\n\nTexte unique XYZ123 avec **gras**."
        md.write_text(content)
        route = respx.post(f"{API}/documents/").mock(
            return_value=Response(201, json=SAMPLE_CREATED)
        )
        result = await docs_create_document(ctx=ctx, title="New Document", file_path=str(md))
        data = json.loads(result)
        assert data["id"] == "aaaa-bbbb-cccc-9999"
        # The exact file content is sent to the client (present in the body).
        assert b"Texte unique XYZ123" in route.calls[0].request.content


# --- docs_delete_document ---


class TestDeleteDocumentTool:
    @respx.mock
    async def test_success_when_creator(self, ctx: MagicMock) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        respx.get(f"{API}/documents/{doc_id}/").mock(
            return_value=Response(200, json=SAMPLE_DOCUMENT_DETAIL)
        )
        respx.get(f"{API}/users/me/").mock(return_value=Response(200, json=SAMPLE_USER))
        delete_route = respx.delete(f"{API}/documents/{doc_id}/").mock(return_value=Response(204))
        result = await docs_delete_document(ctx=ctx, document_id=doc_id)
        data = json.loads(result)
        assert data["status"] == "deleted"
        assert data["document_id"] == doc_id
        assert delete_route.called

    @respx.mock
    async def test_success_when_creator_is_dict(self, ctx: MagicMock) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        detail = {**SAMPLE_DOCUMENT_DETAIL, "creator": {"id": "user-001", "email": "x@y.z"}}
        respx.get(f"{API}/documents/{doc_id}/").mock(return_value=Response(200, json=detail))
        respx.get(f"{API}/users/me/").mock(return_value=Response(200, json=SAMPLE_USER))
        delete_route = respx.delete(f"{API}/documents/{doc_id}/").mock(return_value=Response(204))
        result = await docs_delete_document(ctx=ctx, document_id=doc_id)
        assert json.loads(result)["status"] == "deleted"
        assert delete_route.called

    @respx.mock
    async def test_refused_when_not_creator(self, ctx: MagicMock) -> None:
        doc_id = "aaaa-bbbb-cccc-0002"
        respx.get(f"{API}/documents/{doc_id}/").mock(
            return_value=Response(200, json=SAMPLE_DOCUMENT_DETAIL_OTHER_CREATOR)
        )
        respx.get(f"{API}/users/me/").mock(return_value=Response(200, json=SAMPLE_USER))
        delete_route = respx.delete(f"{API}/documents/{doc_id}/").mock(return_value=Response(204))
        result = await docs_delete_document(ctx=ctx, document_id=doc_id)
        assert "you can only delete documents you created" in result.lower()
        assert delete_route.called is False

    @respx.mock
    async def test_refused_when_creator_missing(self, ctx: MagicMock) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        detail = {k: v for k, v in SAMPLE_DOCUMENT_DETAIL.items() if k != "creator"}
        respx.get(f"{API}/documents/{doc_id}/").mock(return_value=Response(200, json=detail))
        respx.get(f"{API}/users/me/").mock(return_value=Response(200, json=SAMPLE_USER))
        delete_route = respx.delete(f"{API}/documents/{doc_id}/").mock(return_value=Response(204))
        result = await docs_delete_document(ctx=ctx, document_id=doc_id)
        assert "you can only delete documents you created" in result.lower()
        assert delete_route.called is False

    @respx.mock
    async def test_not_found_on_get(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/missing/").mock(return_value=Response(404))
        result = await docs_delete_document(ctx=ctx, document_id="missing")
        assert "not found" in result.lower()

    async def test_empty_id(self, ctx: MagicMock) -> None:
        result = await docs_delete_document(ctx=ctx, document_id="")
        assert "Error" in result


# --- docs_update_document_title ---


class TestUpdateDocumentTitleTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        doc_id = "aaaa-bbbb-cccc-0001"
        respx.patch(f"{API}/documents/{doc_id}/").mock(
            return_value=Response(200, json={"id": doc_id, "title": "New Title"})
        )
        result = await docs_update_document_title(ctx=ctx, document_id=doc_id, title="New Title")
        data = json.loads(result)
        assert data["id"] == doc_id
        assert data["title"] == "New Title"

    @respx.mock
    async def test_not_found(self, ctx: MagicMock) -> None:
        respx.patch(f"{API}/documents/missing/").mock(return_value=Response(404))
        result = await docs_update_document_title(ctx=ctx, document_id="missing", title="X")
        assert "not found" in result.lower()

    async def test_empty_id(self, ctx: MagicMock) -> None:
        result = await docs_update_document_title(ctx=ctx, document_id="", title="X")
        assert "Error" in result

    async def test_empty_title(self, ctx: MagicMock) -> None:
        result = await docs_update_document_title(ctx=ctx, document_id="abc", title="")
        assert "Error" in result


# --- docs_update_document_content ---


class TestUpdateDocumentContentTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        target_id = "aaaa-bbbb-cccc-0001"
        temp_id = "temp-001"
        respx.get(f"{BASE_URL}/collaboration/ydoc/v1/docs/{target_id}").mock(
            return_value=Response(200, json={"doc": yhub_state("ancien")})
        )
        respx.post(f"{API}/documents/").mock(
            return_value=Response(201, json={"id": temp_id, "title": "_mcp_temp_convert"})
        )
        respx.get(f"{BASE_URL}/collaboration/ydoc/v1/docs/{temp_id}").mock(
            return_value=Response(200, json={"doc": yhub_state("nouveau")})
        )
        respx.patch(f"{BASE_URL}/collaboration/ydoc/v1/docs/{target_id}").mock(
            return_value=Response(200)
        )
        respx.delete(f"{API}/documents/{temp_id}/").mock(return_value=Response(204))

        result = await docs_update_document_content(ctx=ctx, document_id=target_id, content="# title")
        data = json.loads(result)
        assert data["id"] == target_id
        assert data["status"] == "updated"

    async def test_empty_id(self, ctx: MagicMock) -> None:
        result = await docs_update_document_content(ctx=ctx, document_id="", content="# x")
        assert "Error" in result

    @respx.mock
    async def test_content_empty_is_valid(self, ctx: MagicMock) -> None:
        """content="" is a valid value that empties the document: it must not
        be rejected and is forwarded to the client as-is."""
        client = ctx.request_context.lifespan_context.client
        with patch.object(
            client, "update_document_content", new=AsyncMock(return_value="abc")
        ) as m:
            result = await docs_update_document_content(ctx=ctx, document_id="abc", content="")
        data = json.loads(result)
        assert data["status"] == "updated"
        m.assert_awaited_once_with("abc", "")

    @respx.mock
    async def test_both_content_and_file_path(self, ctx: MagicMock, tmp_path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# x")
        result = await docs_update_document_content(
            ctx=ctx, document_id="abc", content="# x", file_path=str(f)
        )
        assert "Error" in result

    @respx.mock
    async def test_neither_content_nor_file_path(self, ctx: MagicMock) -> None:
        result = await docs_update_document_content(ctx=ctx, document_id="abc")
        assert "Error" in result

    @respx.mock
    async def test_file_path_txt_and_symlink_refused(self, ctx: MagicMock, tmp_path) -> None:
        txt = tmp_path / "secret.txt"
        txt.write_text("# x")
        res_txt = await docs_update_document_content(
            ctx=ctx, document_id="abc", file_path=str(txt)
        )
        assert "Error" in res_txt
        link = tmp_path / "doc.md"
        link.symlink_to(txt)
        res_link = await docs_update_document_content(
            ctx=ctx, document_id="abc", file_path=str(link)
        )
        assert "Error" in res_link

    @respx.mock
    async def test_file_path_too_large_refused(self, ctx: MagicMock, tmp_path) -> None:
        big = tmp_path / "big.md"
        big.write_bytes(b"x" * (5 * 1024 * 1024 + 10))
        result = await docs_update_document_content(
            ctx=ctx, document_id="abc", file_path=str(big)
        )
        assert "Error" in result

    @respx.mock
    async def test_file_path_valid_sends_exact_content(self, ctx: MagicMock, tmp_path) -> None:
        md = tmp_path / "doc.md"
        content = "# Contenu fichier\n\nUnique token ABCDEFGH."
        md.write_text(content)
        client = ctx.request_context.lifespan_context.client
        with patch.object(
            client, "update_document_content", new=AsyncMock(return_value="abc")
        ) as m:
            result = await docs_update_document_content(
                ctx=ctx, document_id="abc", file_path=str(md)
            )
        data = json.loads(result)
        assert data["status"] == "updated"
        m.assert_awaited_once_with("abc", content)


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
