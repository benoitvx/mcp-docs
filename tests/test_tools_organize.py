"""Tests for organization MCP tools (move, duplicate, trashbin, restore)."""

import json
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from mcp_docs.app import AppContext
from mcp_docs.client import DocsClient
from mcp_docs.tools_organize import (
    docs_duplicate_document,
    docs_list_trashbin,
    docs_move_document,
    docs_restore_document,
)

from .conftest import BASE_URL, SAMPLE_DOCUMENTS, make_config

API = f"{BASE_URL}/api/v1.0"
DOC_ID = "doc-001"
TARGET_ID = "doc-999"


@pytest.fixture
def docs_client() -> DocsClient:
    return DocsClient(make_config())


@pytest.fixture
def ctx(docs_client: DocsClient) -> MagicMock:
    context = MagicMock()
    context.request_context.lifespan_context = AppContext(config=make_config(), client=docs_client)
    return context


class TestMoveDocumentTool:
    @respx.mock
    async def test_success_default_position(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/move/").mock(
            return_value=Response(200, json={"message": "Document moved successfully."})
        )
        result = await docs_move_document(ctx=ctx, document_id=DOC_ID, target_document_id=TARGET_ID)
        data = json.loads(result)
        assert data["status"] == "moved"

    @respx.mock
    async def test_success_first_child(self, ctx: MagicMock) -> None:
        route = respx.post(f"{API}/documents/{DOC_ID}/move/").mock(
            return_value=Response(200, json={"message": "ok"})
        )
        await docs_move_document(
            ctx=ctx, document_id=DOC_ID, target_document_id=TARGET_ID, position="first-child"
        )
        body = json.loads(route.calls[0].request.read())
        assert body["position"] == "first-child"

    async def test_invalid_position(self, ctx: MagicMock) -> None:
        result = await docs_move_document(
            ctx=ctx, document_id=DOC_ID, target_document_id=TARGET_ID, position="upside-down"
        )
        assert "Error" in result

    async def test_empty_target(self, ctx: MagicMock) -> None:
        result = await docs_move_document(ctx=ctx, document_id=DOC_ID, target_document_id="")
        assert "Error" in result

    async def test_empty_id(self, ctx: MagicMock) -> None:
        result = await docs_move_document(ctx=ctx, document_id="", target_document_id=TARGET_ID)
        assert "Error" in result


class TestDuplicateDocumentTool:
    @respx.mock
    async def test_success_default(self, ctx: MagicMock) -> None:
        new_id = "new-doc-123"
        respx.post(f"{API}/documents/{DOC_ID}/duplicate/").mock(
            return_value=Response(201, json={"id": new_id})
        )
        result = await docs_duplicate_document(ctx=ctx, document_id=DOC_ID)
        data = json.loads(result)
        assert data["id"] == new_id
        assert data["status"] == "duplicated"

    @respx.mock
    async def test_with_descendants(self, ctx: MagicMock) -> None:
        route = respx.post(f"{API}/documents/{DOC_ID}/duplicate/").mock(
            return_value=Response(201, json={"id": "x"})
        )
        await docs_duplicate_document(
            ctx=ctx, document_id=DOC_ID, with_descendants=True, with_accesses=True
        )
        body = json.loads(route.calls[0].request.read())
        assert body["with_descendants"] is True
        assert body["with_accesses"] is True

    async def test_empty_id(self, ctx: MagicMock) -> None:
        result = await docs_duplicate_document(ctx=ctx, document_id="")
        assert "Error" in result


class TestListTrashbinTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/trashbin/").mock(
            return_value=Response(200, json=SAMPLE_DOCUMENTS)
        )
        result = await docs_list_trashbin(ctx=ctx)
        data = json.loads(result)
        assert data["count"] == 2

    async def test_invalid_page(self, ctx: MagicMock) -> None:
        result = await docs_list_trashbin(ctx=ctx, page=0)
        assert "Error" in result

    async def test_invalid_page_size(self, ctx: MagicMock) -> None:
        result = await docs_list_trashbin(ctx=ctx, page_size=200)
        assert "Error" in result


class TestRestoreDocumentTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/restore/").mock(
            return_value=Response(200, json={"detail": "restored"})
        )
        result = await docs_restore_document(ctx=ctx, document_id=DOC_ID)
        data = json.loads(result)
        assert data["status"] == "restored"

    @respx.mock
    async def test_not_found(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/missing/restore/").mock(return_value=Response(404))
        result = await docs_restore_document(ctx=ctx, document_id="missing")
        assert "not found" in result.lower()

    async def test_empty_id(self, ctx: MagicMock) -> None:
        result = await docs_restore_document(ctx=ctx, document_id="")
        assert "Error" in result
