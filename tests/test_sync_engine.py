"""End-to-end behaviour of the sync engine against a mocked API and a temp vault."""

from pathlib import Path

import httpx
import pytest
import respx

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig
from mcp_docs.sync import SyncReport, sync_tree
from mcp_docs.vault import read_meta

BASE = "https://docs.example.org"
ROOT = "5b243392-b3a5-4caa-a7e6-e88566e1c72e"
CHILD = "11111111-1111-4111-8111-111111111111"
GRANDCHILD = "33333333-3333-4333-8333-333333333333"


def _doc(
    doc_id: str, title: str, updated_at: str, numchild: int = 0, path: str = "0000AAA"
) -> dict[str, object]:
    return {
        "id": doc_id,
        "title": title,
        "updated_at": updated_at,
        "numchild": numchild,
        "path": path,
        "depth": 1,
    }


def _page(results: list[dict[str, object]]) -> dict[str, object]:
    return {"count": len(results), "next": None, "previous": None, "results": results}


def _mock_tree(
    root_updated: str = "2026-08-01T10:00:00Z",
    child_updated: str = "2026-08-02T10:00:00Z",
    root_title: str = "Racine",
    child_title: str = "Enfant",
    child_body: str = "corps enfant",
) -> tuple[respx.Route, respx.Route]:
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/").mock(
        return_value=httpx.Response(200, json=_doc(ROOT, root_title, root_updated, numchild=1))
    )
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/children/").mock(
        return_value=httpx.Response(
            200, json=_page([_doc(CHILD, child_title, child_updated, path="0000AAA0001")])
        )
    )
    root_content = respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/formatted-content/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": ROOT,
                "title": root_title,
                "content": "corps racine",
                "updated_at": root_updated,
            },
        )
    )
    child_content = respx.get(f"{BASE}/api/v1.0/documents/{CHILD}/formatted-content/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": CHILD,
                "title": child_title,
                "content": child_body,
                "updated_at": child_updated,
            },
        )
    )
    return root_content, child_content


async def _run(vault: Path, dry_run: bool = False, destination: str = "Docs") -> SyncReport:
    client = DocsClient(DocsConfig(base_url=BASE, session_cookie="c"))
    try:
        return await sync_tree(
            client,
            vault_root=vault,
            destination=destination,
            document=f"{BASE}/docs/{ROOT}/",
            dry_run=dry_run,
        )
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_first_sync_creates_the_whole_tree(tmp_path: Path) -> None:
    _mock_tree()
    report = await _run(tmp_path)

    root_note = tmp_path / "Docs" / "Racine" / "Racine.md"
    child_note = tmp_path / "Docs" / "Racine" / "Enfant.md"
    assert root_note.read_text(encoding="utf-8").endswith("corps racine\n")
    assert child_note.exists()
    assert report.created == 2
    assert report.scanned == 2
    meta = read_meta(root_note.read_text(encoding="utf-8"))
    assert meta["docs_id"] == ROOT
    assert meta["docs_url"] == f"{BASE}/docs/{ROOT}/"


@pytest.mark.asyncio
@respx.mock
async def test_second_sync_without_upstream_change_downloads_nothing(tmp_path: Path) -> None:
    root_content, child_content = _mock_tree()
    await _run(tmp_path)
    # respx returns the same Route object when a pattern is re-registered, so the
    # first run's calls stay on the counter — compare a delta, not `.called`.
    before = (root_content.call_count, child_content.call_count)
    _mock_tree()
    report = await _run(tmp_path)

    assert report.unchanged == 2
    assert report.updated == 0
    assert (root_content.call_count, child_content.call_count) == before


@pytest.mark.asyncio
@respx.mock
async def test_only_the_changed_document_is_downloaded(tmp_path: Path) -> None:
    root_content, child_content = _mock_tree()
    await _run(tmp_path)
    before_root, before_child = root_content.call_count, child_content.call_count
    _mock_tree(child_updated="2026-08-09T10:00:00Z", child_body="corps modifié")
    report = await _run(tmp_path)

    assert report.updated == 1
    assert report.unchanged == 1
    assert root_content.call_count == before_root
    assert child_content.call_count == before_child + 1
    child_note = tmp_path / "Docs" / "Racine" / "Enfant.md"
    assert child_note.read_text(encoding="utf-8").endswith("corps modifié\n")


@pytest.mark.asyncio
@respx.mock
async def test_leaf_becoming_a_parent_moves_its_note(tmp_path: Path) -> None:
    _mock_tree()
    await _run(tmp_path)

    _mock_tree()
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/children/").mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [_doc(CHILD, "Enfant", "2026-08-02T10:00:00Z", numchild=1, path="0000AAA0001")]
            ),
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/{CHILD}/children/").mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [_doc(GRANDCHILD, "Petit", "2026-08-03T10:00:00Z", path="0000AAA00010001")]
            ),
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/{GRANDCHILD}/formatted-content/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": GRANDCHILD,
                "title": "Petit",
                "content": "corps petit",
                "updated_at": "2026-08-03T10:00:00Z",
            },
        )
    )
    report = await _run(tmp_path)

    assert not (tmp_path / "Docs" / "Racine" / "Enfant.md").exists()
    moved = tmp_path / "Docs" / "Racine" / "Enfant" / "Enfant.md"
    assert moved.exists()
    assert read_meta(moved.read_text(encoding="utf-8"))["docs_id"] == CHILD
    assert (tmp_path / "Docs" / "Racine" / "Enfant" / "Petit.md").exists()
    assert report.moved == 1


@pytest.mark.asyncio
@respx.mock
async def test_renamed_document_moves_and_is_reported_with_its_origin(tmp_path: Path) -> None:
    _mock_tree()
    await _run(tmp_path)
    _mock_tree(child_title="Enfant renommé")
    report = await _run(tmp_path)

    assert not (tmp_path / "Docs" / "Racine" / "Enfant.md").exists()
    assert (tmp_path / "Docs" / "Racine" / "Enfant renommé.md").exists()
    assert report.moved == 1
    entry = next(change for change in report.changes if change.action == "moved")
    assert entry.from_path is not None
    assert entry.from_path.endswith("Enfant.md")


@pytest.mark.asyncio
@respx.mock
async def test_orphan_is_reported_and_left_untouched(tmp_path: Path) -> None:
    _mock_tree()
    await _run(tmp_path)
    orphan = tmp_path / "Docs" / "Racine" / "Disparu.md"
    orphan.write_text("---\ndocs_id: gone-id\n---\n\nvieux\n", encoding="utf-8")
    _mock_tree()
    report = await _run(tmp_path)

    assert orphan.exists()
    assert [item["title"] for item in report.orphans] == ["Disparu"]


@pytest.mark.asyncio
@respx.mock
async def test_personal_notes_are_never_touched(tmp_path: Path) -> None:
    _mock_tree()
    folder = tmp_path / "Docs" / "Racine"
    folder.mkdir(parents=True)
    (folder / "Mes idées.md").write_text("---\ntags: [x]\n---\n\nà moi\n", encoding="utf-8")
    report = await _run(tmp_path)

    assert (folder / "Mes idées.md").read_text(encoding="utf-8") == "---\ntags: [x]\n---\n\nà moi\n"
    assert report.orphans == []


@pytest.mark.asyncio
@respx.mock
async def test_user_frontmatter_survives_an_update(tmp_path: Path) -> None:
    _mock_tree()
    await _run(tmp_path)
    child_note = tmp_path / "Docs" / "Racine" / "Enfant.md"
    child_note.write_text(
        child_note.read_text(encoding="utf-8").replace("---\n\n", "statut: relu\n---\n\n", 1),
        encoding="utf-8",
    )
    _mock_tree(child_updated="2026-08-09T10:00:00Z", child_body="corps modifié")
    await _run(tmp_path)

    updated = child_note.read_text(encoding="utf-8")
    assert "statut: relu" in updated
    assert updated.endswith("corps modifié\n")


@pytest.mark.asyncio
@respx.mock
async def test_dry_run_writes_nothing_and_downloads_no_content(tmp_path: Path) -> None:
    root_content, child_content = _mock_tree()
    report = await _run(tmp_path, dry_run=True)

    assert report.dry_run is True
    assert report.created == 2
    assert not (tmp_path / "Docs").exists()
    assert not root_content.called
    assert not child_content.called


@pytest.mark.asyncio
@respx.mock
async def test_a_failing_document_does_not_abort_the_others(tmp_path: Path) -> None:
    _mock_tree()
    respx.get(f"{BASE}/api/v1.0/documents/{CHILD}/formatted-content/").mock(
        return_value=httpx.Response(500, json={})
    )
    report = await _run(tmp_path)

    assert (tmp_path / "Docs" / "Racine" / "Racine.md").exists()
    assert len(report.errors) == 1
    assert report.errors[0]["document_id"] == CHILD


@pytest.mark.asyncio
@respx.mock
async def test_in_tree_links_are_rewritten_on_write(tmp_path: Path) -> None:
    _mock_tree(child_body=f"voir [la racine]({BASE}/docs/{ROOT}/)")
    await _run(tmp_path)

    child_note = tmp_path / "Docs" / "Racine" / "Enfant.md"
    assert "[[Racine|la racine]]" in child_note.read_text(encoding="utf-8")


@pytest.mark.asyncio
@respx.mock
async def test_report_names_the_root_folder_as_destination(tmp_path: Path) -> None:
    _mock_tree()
    report = await _run(tmp_path)
    assert report.destination == "Docs/Racine"
    assert report.root_title == "Racine"
