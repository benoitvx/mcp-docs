"""Foundations for the vault sync: tree metadata, vault config, child pagination."""

import httpx
import pytest
import respx

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig
from mcp_docs.models import DocumentSummary

BASE = "https://docs.example.org"


def _node(doc_id: str, **over: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": doc_id,
        "title": f"doc {doc_id}",
        "updated_at": "2026-08-01T10:00:00Z",
        "numchild": 0,
        "path": "0000AAA",
        "depth": 1,
    }
    payload.update(over)
    return payload


def test_document_summary_carries_tree_metadata() -> None:
    doc = DocumentSummary.model_validate(_node("a", numchild=3, depth=2, path="0000AAA0000001"))
    assert doc.numchild == 3
    assert doc.depth == 2
    assert doc.path == "0000AAA0000001"


def test_document_summary_defaults_when_fields_absent() -> None:
    doc = DocumentSummary.model_validate({"id": "a"})
    assert doc.numchild == 0
    assert doc.path is None


def test_config_reads_vault_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCS_VAULT_PATH", "/tmp/vault")
    config = DocsConfig(session_cookie="c")
    assert config.vault_path is not None
    assert str(config.vault_path) == "/tmp/vault"


def test_config_vault_path_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCS_VAULT_PATH", raising=False)
    assert DocsConfig(session_cookie="c").vault_path is None


@pytest.mark.asyncio
@respx.mock
async def test_list_all_children_follows_pagination() -> None:
    respx.get(f"{BASE}/api/v1.0/documents/root/children/", params={"page": "1"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 3,
                "next": f"{BASE}/?page=2",
                "previous": None,
                "results": [_node("a"), _node("b")],
            },
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/root/children/", params={"page": "2"}).mock(
        return_value=httpx.Response(
            200, json={"count": 3, "next": None, "previous": None, "results": [_node("c")]}
        )
    )
    client = DocsClient(DocsConfig(base_url=BASE, session_cookie="c"))
    try:
        children = await client.list_all_children("root")
    finally:
        await client.close()
    assert [c.id for c in children] == ["a", "b", "c"]
