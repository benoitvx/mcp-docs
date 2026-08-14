"""MCP tool wrapping the vault sync engine."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from mcp_docs.app import AppContext
from mcp_docs.client import DocsClient
from mcp_docs.tools_sync import docs_sync_tree

from .conftest import make_config

BASE = "https://docs.example.org"
ROOT = "5b243392-b3a5-4caa-a7e6-e88566e1c72e"


@pytest.fixture
def vault_dir(tmp_path: Path) -> Path:
    """A vault root for sync tests."""
    root = tmp_path / "vault"
    root.mkdir()
    return root


@pytest.fixture
def mock_context(vault_dir: Path) -> MagicMock:
    """Mock MCP Context whose config points at a usable vault."""
    config = make_config(base_url=BASE, vault_path=vault_dir)
    context = MagicMock()
    context.request_context.lifespan_context = AppContext(config=config, client=DocsClient(config))
    return context


@pytest.fixture
def mock_context_no_vault() -> MagicMock:
    """Mock MCP Context with no DOCS_VAULT_PATH configured."""
    config = make_config(base_url=BASE)
    context = MagicMock()
    context.request_context.lifespan_context = AppContext(config=config, client=DocsClient(config))
    return context


def _mock_single_document() -> None:
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": ROOT,
                "title": "Racine",
                "updated_at": "2026-08-01T10:00:00Z",
                "numchild": 0,
                "path": "0000AAA",
                "depth": 1,
            },
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/formatted-content/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": ROOT,
                "title": "Racine",
                "content": "corps",
                "updated_at": "2026-08-01T10:00:00Z",
            },
        )
    )


@pytest.mark.asyncio
async def test_refuses_when_vault_path_is_not_configured(mock_context_no_vault: MagicMock) -> None:
    result = await docs_sync_tree(mock_context_no_vault, document=f"{BASE}/docs/{ROOT}/")
    assert "DOCS_VAULT_PATH" in result


@pytest.mark.asyncio
async def test_rejects_an_empty_document_reference(mock_context: MagicMock) -> None:
    assert "Error" in await docs_sync_tree(mock_context, document="  ")


@pytest.mark.asyncio
async def test_rejects_a_reference_without_uuid(mock_context: MagicMock) -> None:
    result = await docs_sync_tree(mock_context, document="https://docs.example.org/docs/")
    assert "Error" in result


@pytest.mark.asyncio
async def test_rejects_an_absolute_destination(mock_context: MagicMock) -> None:
    assert "Error" in await docs_sync_tree(mock_context, document=ROOT, destination="/etc")


@pytest.mark.asyncio
async def test_rejects_a_traversing_destination(mock_context: MagicMock) -> None:
    assert "Error" in await docs_sync_tree(mock_context, document=ROOT, destination="../../etc")


@pytest.mark.asyncio
@respx.mock
async def test_returns_a_json_report(mock_context: MagicMock, vault_dir: Path) -> None:
    _mock_single_document()
    payload = json.loads(await docs_sync_tree(mock_context, document=f"{BASE}/docs/{ROOT}/"))

    assert payload["root"] == "Racine"
    assert payload["created"] == 1
    assert payload["scanned"] == 1
    assert payload["errors"] == []
    assert (vault_dir / "Docs" / "Racine.md").exists()


@pytest.mark.asyncio
@respx.mock
async def test_dry_run_reports_without_writing(mock_context: MagicMock, vault_dir: Path) -> None:
    _mock_single_document()
    payload = json.loads(
        await docs_sync_tree(mock_context, document=f"{BASE}/docs/{ROOT}/", dry_run=True)
    )

    assert payload["dry_run"] is True
    assert payload["created"] == 1
    assert not (vault_dir / "Docs").exists()
