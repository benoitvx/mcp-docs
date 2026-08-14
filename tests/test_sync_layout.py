"""Tree discovery and folder-note layout."""

from pathlib import PurePosixPath

import httpx
import pytest
import respx

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig
from mcp_docs.sync import TreeNode, discover_tree, parse_document_ref, plan_layout

BASE = "https://docs.example.org"


def node(
    doc_id: str,
    title: str,
    children: tuple[TreeNode, ...] = (),
    updated_at: str = "2026-08-01T10:00:00Z",
    path: str | None = None,
) -> TreeNode:
    kids = list(children)
    return TreeNode(
        id=doc_id,
        title=title,
        updated_at=updated_at,
        numchild=len(kids),
        path=path or f"0000{doc_id}",
        children=kids,
    )


class TestParseDocumentRef:
    def test_extracts_uuid_from_url(self) -> None:
        url = "https://docs.numerique.gouv.fr/docs/5b243392-b3a5-4caa-a7e6-e88566e1c72e/"
        assert parse_document_ref(url) == "5b243392-b3a5-4caa-a7e6-e88566e1c72e"

    def test_accepts_a_bare_uuid_and_lowercases_it(self) -> None:
        assert (
            parse_document_ref("5B243392-B3A5-4CAA-A7E6-E88566E1C72E")
            == "5b243392-b3a5-4caa-a7e6-e88566e1c72e"
        )

    def test_rejects_a_value_without_uuid(self) -> None:
        with pytest.raises(ValueError):
            parse_document_ref("https://docs.numerique.gouv.fr/docs/")


class TestPlanLayout:
    def test_leaf_root_is_a_single_file(self) -> None:
        assert plan_layout(node("r", "Racine")) == {"r": PurePosixPath("Racine.md")}

    def test_parent_becomes_a_folder_note(self) -> None:
        layout = plan_layout(node("r", "Racine", (node("a", "Enfant"),)))
        assert layout["r"] == PurePosixPath("Racine/Racine.md")
        assert layout["a"] == PurePosixPath("Racine/Enfant.md")

    def test_nested_parents_nest_folders(self) -> None:
        tree = node("r", "Racine", (node("a", "Enfant", (node("b", "Petit"),)),))
        layout = plan_layout(tree)
        assert layout["a"] == PurePosixPath("Racine/Enfant/Enfant.md")
        assert layout["b"] == PurePosixPath("Racine/Enfant/Petit.md")

    def test_titles_are_sanitized(self) -> None:
        tree = node("r", "Racine", (node("a", "Feedbacks / intérêt"),))
        assert plan_layout(tree)["a"] == PurePosixPath("Racine/Feedbacks - intérêt.md")

    def test_sibling_collision_is_suffixed_by_materialized_path_order(self) -> None:
        tree = node(
            "r",
            "Racine",
            (node("a", "A/B", path="0000AAA2"), node("b", "A:B", path="0000AAA1")),
        )
        layout = plan_layout(tree)
        # "b" sorts first on its materialized path, so it keeps the bare name.
        assert layout["b"] == PurePosixPath("Racine/A-B.md")
        assert layout["a"] == PurePosixPath("Racine/A-B (2).md")

    def test_collision_resolution_is_stable_across_runs(self) -> None:
        tree = node(
            "r",
            "Racine",
            (node("a", "A/B", path="0000AAA2"), node("b", "A:B", path="0000AAA1")),
        )
        assert plan_layout(tree) == plan_layout(tree)

    def test_same_name_in_different_folders_does_not_collide(self) -> None:
        tree = node(
            "r",
            "Racine",
            (
                node("a", "Notes", (node("c", "Transcript"),)),
                node("b", "Autres", (node("d", "Transcript"),)),
            ),
        )
        layout = plan_layout(tree)
        assert layout["c"] == PurePosixPath("Racine/Notes/Transcript.md")
        assert layout["d"] == PurePosixPath("Racine/Autres/Transcript.md")


def _payload(doc_id: str, title: str, numchild: int = 0, path: str = "0000AAA") -> dict[str, object]:
    return {
        "id": doc_id,
        "title": title,
        "updated_at": "2026-08-01T10:00:00Z",
        "numchild": numchild,
        "path": path,
        "depth": 1,
    }


@pytest.mark.asyncio
@respx.mock
async def test_discover_tree_walks_every_level() -> None:
    respx.get(f"{BASE}/api/v1.0/documents/root/").mock(
        return_value=httpx.Response(200, json=_payload("root", "Racine", numchild=2))
    )
    respx.get(f"{BASE}/api/v1.0/documents/root/children/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "next": None,
                "previous": None,
                "results": [
                    _payload("a", "A", numchild=1, path="0000AAA1"),
                    _payload("b", "B", path="0000AAA2"),
                ],
            },
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/a/children/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [_payload("c", "C", path="0000AAA10001")],
            },
        )
    )
    client = DocsClient(DocsConfig(base_url=BASE, session_cookie="c"))
    try:
        tree = await discover_tree(client, "root")
    finally:
        await client.close()

    assert tree.id == "root"
    assert [child.id for child in tree.children] == ["a", "b"]
    assert [child.id for child in tree.children[0].children] == ["c"]


@pytest.mark.asyncio
@respx.mock
async def test_discover_tree_does_not_fetch_children_of_leaves() -> None:
    respx.get(f"{BASE}/api/v1.0/documents/root/").mock(
        return_value=httpx.Response(200, json=_payload("root", "Racine"))
    )
    route = respx.get(f"{BASE}/api/v1.0/documents/root/children/").mock(
        return_value=httpx.Response(
            200, json={"count": 0, "next": None, "previous": None, "results": []}
        )
    )
    client = DocsClient(DocsConfig(base_url=BASE, session_cookie="c"))
    try:
        tree = await discover_tree(client, "root")
    finally:
        await client.close()
    assert tree.children == []
    assert not route.called
