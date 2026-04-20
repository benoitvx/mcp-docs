"""Tests for link sharing and favorites MCP tools."""

import json
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from mcp_docs.app import AppContext
from mcp_docs.client import DocsClient
from mcp_docs.tools_sharing import (
    docs_add_favorite,
    docs_list_favorites,
    docs_remove_favorite,
    docs_update_link_configuration,
)

from .conftest import BASE_URL, SAMPLE_DOCUMENTS, make_config

API = f"{BASE_URL}/api/v1.0"
DOC_ID = "doc-001"


@pytest.fixture
def docs_client() -> DocsClient:
    return DocsClient(make_config())


@pytest.fixture
def ctx(docs_client: DocsClient) -> MagicMock:
    context = MagicMock()
    context.request_context.lifespan_context = AppContext(config=make_config(), client=docs_client)
    return context


class TestUpdateLinkConfigurationTool:
    @respx.mock
    async def test_public_reader(self, ctx: MagicMock) -> None:
        respx.put(f"{API}/documents/{DOC_ID}/link-configuration/").mock(
            return_value=Response(200, json={"link_reach": "public", "link_role": "reader"})
        )
        result = await docs_update_link_configuration(
            ctx=ctx, document_id=DOC_ID, link_reach="public", link_role="reader"
        )
        data = json.loads(result)
        assert data["link_reach"] == "public"
        assert data["link_role"] == "reader"

    @respx.mock
    async def test_restricted_without_role(self, ctx: MagicMock) -> None:
        respx.put(f"{API}/documents/{DOC_ID}/link-configuration/").mock(
            return_value=Response(200, json={"link_reach": "restricted", "link_role": None})
        )
        result = await docs_update_link_configuration(ctx=ctx, document_id=DOC_ID, link_reach="restricted")
        data = json.loads(result)
        assert data["link_reach"] == "restricted"
        assert data["link_role"] is None

    async def test_restricted_with_role_rejected(self, ctx: MagicMock) -> None:
        result = await docs_update_link_configuration(
            ctx=ctx, document_id=DOC_ID, link_reach="restricted", link_role="reader"
        )
        assert "Error" in result

    async def test_public_without_role_rejected(self, ctx: MagicMock) -> None:
        result = await docs_update_link_configuration(ctx=ctx, document_id=DOC_ID, link_reach="public")
        assert "Error" in result

    async def test_invalid_reach(self, ctx: MagicMock) -> None:
        result = await docs_update_link_configuration(
            ctx=ctx, document_id=DOC_ID, link_reach="world-wide", link_role="reader"
        )
        assert "Error" in result

    async def test_invalid_role(self, ctx: MagicMock) -> None:
        result = await docs_update_link_configuration(
            ctx=ctx, document_id=DOC_ID, link_reach="public", link_role="god"
        )
        assert "Error" in result

    async def test_empty_document_id(self, ctx: MagicMock) -> None:
        result = await docs_update_link_configuration(ctx=ctx, document_id="", link_reach="public", link_role="reader")
        assert "Error" in result


class TestListFavoritesTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/favorite_list/").mock(
            return_value=Response(200, json=SAMPLE_DOCUMENTS)
        )
        result = await docs_list_favorites(ctx=ctx)
        data = json.loads(result)
        assert data["count"] == 2
        assert len(data["documents"]) == 2

    async def test_invalid_page(self, ctx: MagicMock) -> None:
        result = await docs_list_favorites(ctx=ctx, page=0)
        assert "Error" in result

    async def test_invalid_page_size(self, ctx: MagicMock) -> None:
        result = await docs_list_favorites(ctx=ctx, page_size=200)
        assert "Error" in result


class TestAddFavoriteTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/favorite/").mock(
            return_value=Response(201, json={"detail": "Document marked as favorite"})
        )
        result = await docs_add_favorite(ctx=ctx, document_id=DOC_ID)
        data = json.loads(result)
        assert data["status"] == "favorited"
        assert data["document_id"] == DOC_ID

    async def test_empty_document_id(self, ctx: MagicMock) -> None:
        result = await docs_add_favorite(ctx=ctx, document_id="")
        assert "Error" in result


class TestRemoveFavoriteTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.delete(f"{API}/documents/{DOC_ID}/favorite/").mock(return_value=Response(204))
        result = await docs_remove_favorite(ctx=ctx, document_id=DOC_ID)
        data = json.loads(result)
        assert data["status"] == "unfavorited"

    async def test_empty_document_id(self, ctx: MagicMock) -> None:
        result = await docs_remove_favorite(ctx=ctx, document_id="")
        assert "Error" in result
