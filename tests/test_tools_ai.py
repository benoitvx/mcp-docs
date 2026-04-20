"""Tests for AI MCP tools."""

import json
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from mcp_docs.app import AppContext
from mcp_docs.client import DocsClient
from mcp_docs.tools_ai import docs_ai_transform, docs_ai_translate

from .conftest import BASE_URL, make_config

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


class TestAITransformTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/ai-transform/").mock(
            return_value=Response(200, json={"answer": "This is a summary."})
        )
        result = await docs_ai_transform(ctx=ctx, document_id=DOC_ID, text="Long text here", action="summarize")
        data = json.loads(result)
        assert data["transformed_text"] == "This is a summary."

    @respx.mock
    async def test_old_response_shape(self, ctx: MagicMock) -> None:
        """Fallback to legacy 'transformed_text' field if 'answer' absent."""
        respx.post(f"{API}/documents/{DOC_ID}/ai-transform/").mock(
            return_value=Response(200, json={"transformed_text": "corrected"})
        )
        result = await docs_ai_transform(ctx=ctx, document_id=DOC_ID, text="hllo", action="correct")
        data = json.loads(result)
        assert data["transformed_text"] == "corrected"

    async def test_invalid_action(self, ctx: MagicMock) -> None:
        result = await docs_ai_transform(ctx=ctx, document_id=DOC_ID, text="x", action="shuffle")
        assert "Error" in result

    async def test_empty_text(self, ctx: MagicMock) -> None:
        result = await docs_ai_transform(ctx=ctx, document_id=DOC_ID, text="", action="correct")
        assert "Error" in result

    async def test_empty_document_id(self, ctx: MagicMock) -> None:
        result = await docs_ai_transform(ctx=ctx, document_id="", text="x", action="correct")
        assert "Error" in result

    @respx.mock
    async def test_permission_error(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/ai-transform/").mock(return_value=Response(403))
        result = await docs_ai_transform(ctx=ctx, document_id=DOC_ID, text="x", action="correct")
        assert "Access denied" in result


class TestAITranslateTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/ai-translate/").mock(
            return_value=Response(200, json={"answer": "Hello world"})
        )
        result = await docs_ai_translate(ctx=ctx, document_id=DOC_ID, text="Bonjour le monde", language="en")
        data = json.loads(result)
        assert data["translated_text"] == "Hello world"

    async def test_empty_language(self, ctx: MagicMock) -> None:
        result = await docs_ai_translate(ctx=ctx, document_id=DOC_ID, text="x", language="")
        assert "Error" in result

    async def test_empty_text(self, ctx: MagicMock) -> None:
        result = await docs_ai_translate(ctx=ctx, document_id=DOC_ID, text="", language="en")
        assert "Error" in result

    async def test_empty_document_id(self, ctx: MagicMock) -> None:
        result = await docs_ai_translate(ctx=ctx, document_id="", text="x", language="en")
        assert "Error" in result
