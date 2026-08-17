"""End-to-end behaviour of the sync engine against a mocked API and a temp vault."""

from pathlib import Path

import httpx
import pytest
import respx

import mcp_docs.sync as sync_module
from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig
from mcp_docs.sync import SyncReport, sync_tree
from mcp_docs.vault import read_meta

BASE = "https://docs.example.org"
ROOT = "5b243392-b3a5-4caa-a7e6-e88566e1c72e"
CHILD = "11111111-1111-4111-8111-111111111111"
SIBLING = "22222222-2222-4222-8222-222222222222"
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
async def test_existing_notes_are_updated_where_they_already_live(tmp_path: Path) -> None:
    """A document already mirrored elsewhere is refreshed in place, not duplicated."""
    _mock_tree()
    await _run(tmp_path, destination="Miroir")

    _mock_tree(child_updated="2026-08-09T10:00:00Z", child_body="corps modifié")
    report = await _run(tmp_path, destination="Docs")

    assert not (tmp_path / "Docs").exists()
    assert report.created == 0
    assert report.updated == 1
    assert report.unchanged == 1
    child = tmp_path / "Miroir" / "Racine" / "Enfant.md"
    assert child.read_text(encoding="utf-8").endswith("corps modifié\n")


@pytest.mark.asyncio
@respx.mock
async def test_untouched_sibling_is_not_rewritten_when_syncing_in_place(tmp_path: Path) -> None:
    _mock_tree()
    await _run(tmp_path, destination="Miroir")
    root_note = tmp_path / "Miroir" / "Racine" / "Racine.md"
    before = root_note.read_text(encoding="utf-8")

    _mock_tree(child_updated="2026-08-09T10:00:00Z", child_body="corps modifié")
    await _run(tmp_path, destination="Docs")

    assert root_note.read_text(encoding="utf-8") == before


@pytest.mark.asyncio
@respx.mock
async def test_notes_from_another_mirror_are_not_reported_as_orphans(tmp_path: Path) -> None:
    _mock_tree()
    await _run(tmp_path, destination="Miroir")
    elsewhere = tmp_path / "Ailleurs"
    elsewhere.mkdir()
    (elsewhere / "Autre.md").write_text("---\ndocs_id: autre-id\n---\n\nx\n", encoding="utf-8")

    _mock_tree()
    report = await _run(tmp_path, destination="Miroir")

    assert report.orphans == []


@pytest.mark.asyncio
@respx.mock
async def test_report_names_the_root_folder_as_destination(tmp_path: Path) -> None:
    _mock_tree()
    report = await _run(tmp_path)
    assert report.destination == "Docs/Racine"
    assert report.root_title == "Racine"


# --- Write collisions -------------------------------------------------------
#
# A sync run must never write onto a file that is not already the note of the
# document being written. Every case below used to end in a silently destroyed
# file and a report claiming success.


def _mock_siblings(*children: tuple[str, str], updated: str = "2026-08-02T10:00:00Z") -> None:
    """Mock a root whose children are the given ``(uuid, title)`` pairs.

    Materialized paths follow the argument order, which is what fixes the
    suffix a sibling gets when two titles sanitize to the same file name.
    """
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/").mock(
        return_value=httpx.Response(
            200, json=_doc(ROOT, "Racine", "2026-08-01T10:00:00Z", numchild=len(children))
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/children/").mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [
                    _doc(uuid, title, updated, path=f"0000AAA000{rank}")
                    for rank, (uuid, title) in enumerate(children, start=1)
                ]
            ),
        )
    )
    for uuid, title in ((ROOT, "Racine"), *children):
        respx.get(f"{BASE}/api/v1.0/documents/{uuid}/formatted-content/").mock(
            return_value=httpx.Response(
                200,
                json={"id": uuid, "title": title, "content": f"corps {title}", "updated_at": updated},
            )
        )


@pytest.mark.asyncio
@respx.mock
async def test_orphan_is_not_overwritten_by_the_sibling_taking_its_name(tmp_path: Path) -> None:
    """Two siblings share a title, so the second is suffixed. When the first is
    deleted upstream its note becomes an orphan the sync promises never to
    touch — including when the survivor reverts to the bare name."""
    _mock_siblings((CHILD, "Projet"), (SIBLING, "Projet"))
    await _run(tmp_path)
    orphan = tmp_path / "Docs" / "Racine" / "Projet.md"
    survivor = tmp_path / "Docs" / "Racine" / "Projet (2).md"
    assert read_meta(orphan.read_text(encoding="utf-8"))["docs_id"] == CHILD
    assert read_meta(survivor.read_text(encoding="utf-8"))["docs_id"] == SIBLING

    respx.clear()
    _mock_siblings((SIBLING, "Projet"), updated="2026-08-09T10:00:00Z")
    report = await _run(tmp_path)

    assert read_meta(orphan.read_text(encoding="utf-8"))["docs_id"] == CHILD
    assert survivor.exists()
    assert report.moved == 0
    assert [(e["document_id"], e["reason"]) for e in report.errors] == [
        (SIBLING, "target_occupied")
    ]
    assert [o["document_id"] for o in report.orphans] == [CHILD]


@pytest.mark.asyncio
@respx.mock
async def test_swapped_sibling_names_lose_nothing_and_converge(tmp_path: Path) -> None:
    """One sibling claims the file name the other is vacating in the same run.
    The clash is refused instead of resolved destructively, and the run that
    follows completes the move once the name is actually free."""
    _mock_siblings((CHILD, "Alpha"), (SIBLING, "Beta"))
    await _run(tmp_path)

    respx.clear()
    _mock_siblings((CHILD, "Beta"), (SIBLING, "Gamma"), updated="2026-08-09T10:00:00Z")
    first = await _run(tmp_path)

    folder = tmp_path / "Docs" / "Racine"
    assert [(e["document_id"], e["reason"]) for e in first.errors] == [(CHILD, "target_occupied")]
    assert sorted(p.name for p in folder.glob("*.md")) == ["Alpha.md", "Gamma.md", "Racine.md"]

    respx.clear()
    _mock_siblings((CHILD, "Beta"), (SIBLING, "Gamma"), updated="2026-08-09T10:00:00Z")
    second = await _run(tmp_path)

    assert second.errors == []
    assert sorted(p.name for p in folder.glob("*.md")) == ["Beta.md", "Gamma.md", "Racine.md"]
    assert read_meta((folder / "Beta.md").read_text(encoding="utf-8"))["docs_id"] == CHILD


@pytest.mark.asyncio
@respx.mock
async def test_creation_does_not_overwrite_a_personal_note(tmp_path: Path) -> None:
    """A note the user wrote carries no docs_id, so it never enters the index.
    A new document landing on its path must still leave it alone."""
    _mock_tree()
    personal = tmp_path / "Docs" / "Racine" / "Enfant.md"
    personal.parent.mkdir(parents=True)
    personal.write_text("mes notes à moi\n", encoding="utf-8")

    report = await _run(tmp_path)

    assert personal.read_text(encoding="utf-8") == "mes notes à moi\n"
    assert (tmp_path / "Docs" / "Racine" / "Racine.md").exists()
    assert report.created == 1
    assert [(e["document_id"], e["reason"]) for e in report.errors] == [(CHILD, "target_occupied")]


@pytest.mark.asyncio
@respx.mock
async def test_creation_does_not_overwrite_another_documents_note(tmp_path: Path) -> None:
    """The occupant belongs to a document outside this tree — still off limits."""
    _mock_tree()
    foreign = tmp_path / "Docs" / "Racine" / "Enfant.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_text(
        f"---\ndocs_id: {GRANDCHILD}\n---\n\ncontenu d'un autre document\n", encoding="utf-8"
    )

    report = await _run(tmp_path)

    assert foreign.read_text(encoding="utf-8").endswith("contenu d'un autre document\n")
    assert [(e["document_id"], e["reason"]) for e in report.errors] == [(CHILD, "target_occupied")]


@pytest.mark.asyncio
@respx.mock
async def test_unreadable_note_does_not_abort_the_run(tmp_path: Path) -> None:
    """A file that is not valid UTF-8 never enters the index, so it looks like a
    free slot. It is skipped with an error and the rest of the tree still lands."""
    _mock_tree()
    broken = tmp_path / "Docs" / "Racine" / "Enfant.md"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"caf\xe9 encod\xe9 en latin-1")

    report = await _run(tmp_path)

    assert (tmp_path / "Docs" / "Racine" / "Racine.md").exists()
    assert broken.read_bytes() == b"caf\xe9 encod\xe9 en latin-1"
    assert report.errors[0]["document_id"] == CHILD


@pytest.mark.asyncio
@respx.mock
async def test_unforeseen_failure_is_reported_without_discarding_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gather backstop: one document failing in a way nobody anticipated must
    not throw away the report for the documents that did succeed."""
    _mock_tree()
    real_apply = sync_module._apply

    async def exploding(client, report, node, target, current, stale, names):  # type: ignore[no-untyped-def]
        if node.id == CHILD:
            raise RuntimeError("boom")
        return await real_apply(client, report, node, target, current, stale, names)

    monkeypatch.setattr(sync_module, "_apply", exploding)
    report = await _run(tmp_path)

    assert (tmp_path / "Docs" / "Racine" / "Racine.md").exists()
    assert report.errors == [
        {"document_id": CHILD, "title": "Enfant", "reason": "RuntimeError"}
    ]


# --- Pruning stays inside the folder this run owns ---------------------------


@pytest.mark.asyncio
@respx.mock
async def test_user_folders_under_the_destination_are_left_alone(tmp_path: Path) -> None:
    """Empty folders the user keeps under the destination are not this sync's
    business. Pruning the whole destination used to delete them silently."""
    _mock_tree()
    templates = tmp_path / "Docs" / "Templates"
    attachments = tmp_path / "Docs" / "attachments"
    templates.mkdir(parents=True)
    attachments.mkdir(parents=True)

    await _run(tmp_path)

    assert templates.is_dir()
    assert attachments.is_dir()


@pytest.mark.asyncio
@respx.mock
async def test_folder_emptied_by_the_run_is_still_pruned(tmp_path: Path) -> None:
    """Narrowing the prune scope must not stop it doing its actual job: a folder
    the run empties by renaming its parent still goes away."""
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
            json=_page([_doc(GRANDCHILD, "Petit", "2026-08-03T10:00:00Z", path="0000AAA00010001")]),
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
    await _run(tmp_path)
    assert (tmp_path / "Docs" / "Racine" / "Enfant" / "Petit.md").exists()

    respx.clear()
    _mock_tree(child_title="Renommé")
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/children/").mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [_doc(CHILD, "Renommé", "2026-08-02T10:00:00Z", numchild=1, path="0000AAA0001")]
            ),
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/{CHILD}/children/").mock(
        return_value=httpx.Response(
            200,
            json=_page([_doc(GRANDCHILD, "Petit", "2026-08-03T10:00:00Z", path="0000AAA00010001")]),
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

    assert (tmp_path / "Docs" / "Racine" / "Renommé" / "Renommé.md").exists()
    assert (tmp_path / "Docs" / "Racine" / "Renommé" / "Petit.md").exists()
    assert not (tmp_path / "Docs" / "Racine" / "Enfant").exists()
    assert report.errors == []
