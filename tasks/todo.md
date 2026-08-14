# Todo — Synchronisation Docs → Obsidian

**Goal:** un tool MCP `docs_sync_tree` qui réplique l'arbre d'un document Docs dans le vault
Obsidian, en ne téléchargeant que ce qui a changé.

**Architecture:** un moteur (`sync.py`) qui ne connaît ni MCP ni système de fichiers au-delà
d'une racine, une couche vault (`vault.py`) qui possède le nommage, le frontmatter et les
écritures sûres, et un tool MCP mince (`tools_sync.py`). Découverte récursive via
`/children/`, comparaison sur `updated_at`, écrasement sans condition.

**Tech Stack:** Python 3.12, httpx, pydantic, pytest + respx, `tmp_path`.

**Spec:** [docs/superpowers/specs/2026-08-14-sync-obsidian-design.md](../docs/superpowers/specs/2026-08-14-sync-obsidian-design.md)

## Global Constraints

- Code, noms et commentaires en anglais ; messages de commit en anglais (gitmoji) ; docs en français.
- `ruff` line-length 120, `select = ["E", "F", "I", "W", "UP"]`. `pyright` en mode `standard`.
- Aucun appel réseau réel dans les tests : `respx` obligatoire.
- Aucun cookie, token ni chemin absolu de credential dans un message d'erreur ou un rapport.
- Toute écriture est confinée sous `DOCS_VAULT_PATH`, vérifiée après `resolve()`.
- Aucune suppression de fichier. Seuls les dossiers devenus vides sous la destination sont retirés.
- Le moteur (`sync.py`, `vault.py`) n'importe rien de `mcp`.

---

## Task 1: Fondations — modèles, config, pagination des enfants

**Files:**
- Modify: `src/mcp_docs/models.py`
- Modify: `src/mcp_docs/config.py`
- Modify: `src/mcp_docs/client.py`
- Test: `tests/test_sync_foundations.py`

**Interfaces:**
- Produces: `DocumentSummary.numchild: int`, `.path: str | None`, `.depth: int | None` ;
  `DocsConfig.vault_path: Path | None` ; `DocsClient.list_all_children(document_id) -> list[DocumentSummary]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sync_foundations.py
"""Foundations for the vault sync: tree metadata, vault config, child pagination."""

import httpx
import pytest
import respx

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig
from mcp_docs.models import DocumentSummary

BASE = "https://docs.example.org"


def _node(doc_id: str, **over):
    payload = {
        "id": doc_id,
        "title": f"doc {doc_id}",
        "updated_at": "2026-08-01T10:00:00Z",
        "numchild": 0,
        "path": "0000AAA",
        "depth": 1,
    }
    payload.update(over)
    return payload


def test_document_summary_carries_tree_metadata():
    doc = DocumentSummary.model_validate(_node("a", numchild=3, depth=2, path="0000AAA0000001"))
    assert doc.numchild == 3
    assert doc.depth == 2
    assert doc.path == "0000AAA0000001"


def test_document_summary_defaults_when_fields_absent():
    doc = DocumentSummary.model_validate({"id": "a"})
    assert doc.numchild == 0
    assert doc.path is None


def test_config_reads_vault_path(monkeypatch):
    monkeypatch.setenv("DOCS_VAULT_PATH", "/tmp/vault")
    config = DocsConfig(session_cookie="c")
    assert config.vault_path is not None
    assert str(config.vault_path) == "/tmp/vault"


def test_config_vault_path_defaults_to_none():
    assert DocsConfig(session_cookie="c").vault_path is None


@pytest.mark.asyncio
@respx.mock
async def test_list_all_children_follows_pagination():
    respx.get(f"{BASE}/api/v1.0/documents/root/children/", params={"page": "1"}).mock(
        return_value=httpx.Response(
            200,
            json={"count": 3, "next": f"{BASE}/?page=2", "previous": None,
                  "results": [_node("a"), _node("b")]},
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_sync_foundations.py -v`
Expected: FAIL — `numchild` absent du modèle, `vault_path` absent de la config,
`list_all_children` non défini.

- [ ] **Step 3: Extend `DocumentSummary`**

Dans `src/mcp_docs/models.py`, ajouter à `DocumentSummary` (après `creator`) :

```python
    numchild: int = 0
    path: str | None = None
    depth: int | None = None
```

- [ ] **Step 4: Add `vault_path` to the config**

Dans `src/mcp_docs/config.py`, ajouter au corps de `DocsConfig`, après `oidc_token` :

```python
    vault_path: Path | None = None
```

`Path` est déjà importé et `env_prefix="DOCS_"` fait le reste : la variable lue est
`DOCS_VAULT_PATH`.

- [ ] **Step 5: Add `list_all_children` to the client**

Dans `src/mcp_docs/client.py`, juste après `list_children` :

```python
    async def list_all_children(self, document_id: str) -> list[DocumentSummary]:
        """List every child of a document, following pagination to the last page.

        The tree sync needs the complete sibling set to lay out folders, and
        ``/children/`` caps a page at 100 entries.
        """
        collected: list[DocumentSummary] = []
        page = 1
        while True:
            response = await self.list_children(document_id, page=page, page_size=100)
            collected.extend(response.results)
            if not response.next:
                return collected
            page += 1
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_sync_foundations.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add src/mcp_docs/models.py src/mcp_docs/config.py src/mcp_docs/client.py tests/test_sync_foundations.py
git commit -m "✨(client) expose tree metadata, vault path config and child pagination"
```

---

## Task 2: Couche vault — nommage, frontmatter, écriture sûre

**Files:**
- Create: `src/mcp_docs/vault.py`
- Test: `tests/test_vault.py`

**Interfaces:**
- Produces: `sanitize_name(title) -> str` ; `split_frontmatter(text) -> tuple[list[str], str]` ;
  `read_meta(text) -> dict[str, str]` ; `compose(meta, body, existing=None) -> str` ;
  `write_atomic(path, text) -> None` ; `resolve_within(root, relative) -> Path` ;
  `index_vault(root) -> dict[str, Path]` ; `prune_empty_dirs(root) -> None` ;
  exception `VaultPathError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vault.py
"""Filesystem layer of the vault sync: naming, frontmatter, safe writes."""

import pytest

from mcp_docs.vault import (
    VaultPathError,
    compose,
    index_vault,
    prune_empty_dirs,
    read_meta,
    resolve_within,
    sanitize_name,
    split_frontmatter,
    write_atomic,
)


class TestSanitizeName:
    def test_strips_zero_width_characters(self):
        assert sanitize_name("🧩 ​Features") == "🧩 Features"

    def test_replaces_path_and_reserved_characters(self):
        assert sanitize_name("💜 Feedbacks / intérêt Hub") == "💜 Feedbacks - intérêt Hub"
        assert sanitize_name("Nom du produit : Tchap") == "Nom du produit - Tchap"

    def test_keeps_emoji(self):
        assert sanitize_name("🐙 LaSuite - Équipe Hub") == "🐙 LaSuite - Équipe Hub"

    def test_collapses_whitespace_and_trailing_dots(self):
        assert sanitize_name("  a   b  ...") == "a b"

    def test_empty_title_falls_back(self):
        assert sanitize_name("") == "sans-titre"
        assert sanitize_name("​  ") == "sans-titre"

    def test_truncates_on_byte_boundary(self):
        name = sanitize_name("é" * 200)
        assert len(name.encode("utf-8")) <= 120
        assert "�" not in name


class TestFrontmatter:
    def test_split_returns_lines_and_body(self):
        lines, body = split_frontmatter("---\na: 1\nb: 2\n---\n\nhello\n")
        assert lines == ["a: 1", "b: 2"]
        assert body == "hello\n"

    def test_split_without_frontmatter(self):
        assert split_frontmatter("hello\n") == ([], "hello\n")

    def test_split_with_unterminated_fence(self):
        assert split_frontmatter("---\na: 1\n") == ([], "---\na: 1\n")

    def test_read_meta_extracts_docs_keys_only(self):
        meta = read_meta('---\ndocs_id: abc\ntags: [x]\ndocs_title: "a: b"\n---\n\nbody\n')
        assert meta == {"docs_id": "abc", "docs_title": "a: b"}

    def test_compose_writes_frontmatter_then_body(self):
        text = compose({"docs_id": "abc"}, "hello")
        assert text == "---\ndocs_id: abc\n---\n\nhello\n"

    def test_compose_quotes_values_needing_it(self):
        text = compose({"docs_title": "Nom : Tchap"}, "x")
        assert 'docs_title: "Nom : Tchap"' in text

    def test_compose_preserves_user_frontmatter(self):
        existing = "---\ndocs_id: old\ntags:\n  - projet\nstatut: en cours\n---\n\nvieux corps\n"
        text = compose({"docs_id": "new"}, "nouveau corps", existing=existing)
        assert "docs_id: new" in text
        assert "docs_id: old" not in text
        assert "tags:\n  - projet" in text
        assert "statut: en cours" in text
        assert text.endswith("nouveau corps\n")


class TestWriteAtomic:
    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "a" / "b" / "c.md"
        write_atomic(target, "hello\n")
        assert target.read_text(encoding="utf-8") == "hello\n"

    def test_leaves_no_temporary_file(self, tmp_path):
        target = tmp_path / "c.md"
        write_atomic(target, "hello\n")
        assert [p.name for p in tmp_path.iterdir()] == ["c.md"]


class TestResolveWithin:
    def test_accepts_a_path_inside_the_root(self, tmp_path):
        assert resolve_within(tmp_path, "Docs/a.md") == (tmp_path / "Docs" / "a.md").resolve()

    def test_rejects_parent_traversal(self, tmp_path):
        with pytest.raises(VaultPathError):
            resolve_within(tmp_path, "../escape.md")

    def test_rejects_absolute_path(self, tmp_path):
        with pytest.raises(VaultPathError):
            resolve_within(tmp_path, "/etc/passwd")

    def test_rejects_symlink_escaping_the_root(self, tmp_path):
        outside = tmp_path.parent / "outside_vault"
        outside.mkdir(exist_ok=True)
        root = tmp_path / "vault"
        root.mkdir()
        (root / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(VaultPathError):
            resolve_within(root, "link/note.md")


class TestIndexVault:
    def test_maps_docs_id_to_path(self, tmp_path):
        write_atomic(tmp_path / "a.md", compose({"docs_id": "id-a"}, "a"))
        write_atomic(tmp_path / "sub" / "b.md", compose({"docs_id": "id-b"}, "b"))
        index = index_vault(tmp_path)
        assert index == {"id-a": tmp_path / "a.md", "id-b": tmp_path / "sub" / "b.md"}

    def test_ignores_notes_without_docs_id(self, tmp_path):
        (tmp_path / "perso.md").write_text("---\ntags: [x]\n---\n\nma note\n", encoding="utf-8")
        assert index_vault(tmp_path) == {}

    def test_missing_root_yields_empty_index(self, tmp_path):
        assert index_vault(tmp_path / "nope") == {}


class TestPruneEmptyDirs:
    def test_removes_empty_directories_only(self, tmp_path):
        (tmp_path / "empty" / "deeper").mkdir(parents=True)
        write_atomic(tmp_path / "full" / "a.md", "x\n")
        prune_empty_dirs(tmp_path)
        assert not (tmp_path / "empty").exists()
        assert (tmp_path / "full" / "a.md").exists()
        assert tmp_path.exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_vault.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_docs.vault'`

- [ ] **Step 3: Write `src/mcp_docs/vault.py`**

```python
"""Filesystem layer for the Obsidian vault sync.

Owns everything that touches disk: turning document titles into safe file
names, reading and rebuilding frontmatter, atomic writes, and the guard that
keeps every path inside the configured vault root.
"""

import os
import re
import unicodedata
from pathlib import Path

_ZERO_WIDTH = "​‌‍﻿"
_RESERVED = '/\\:*?"<>|'
_MAX_NAME_BYTES = 120
_FALLBACK_NAME = "sans-titre"
_DOCS_KEY = re.compile(r"\s*docs_[A-Za-z0-9_]*\s*:")
_NEEDS_QUOTING = set(":#\"'\n{}[],&*!|>%@`")


class VaultPathError(ValueError):
    """Raised when a path would resolve outside the vault root."""


def _truncate_bytes(value: str, limit: int) -> str:
    """Cut `value` to `limit` UTF-8 bytes without splitting a character."""
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def sanitize_name(title: str) -> str:
    """Turn a document title into a file name that is safe on macOS and legible.

    Emoji are kept on purpose: they carry meaning in this vault and both the
    filesystem and Obsidian handle them. Identity lives in the frontmatter
    ``docs_id``, so a lossy name is never a correctness problem.
    """
    name = "".join(
        character
        for character in (title or "")
        if character not in _ZERO_WIDTH and unicodedata.category(character) != "Cc"
    )
    name = "".join("-" if character in _RESERVED else character for character in name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(".").strip()
    name = _truncate_bytes(name, _MAX_NAME_BYTES).strip()
    return name or _FALLBACK_NAME


def split_frontmatter(text: str) -> tuple[list[str], str]:
    """Split a note into its frontmatter lines (fences excluded) and its body."""
    if not text.startswith("---\n"):
        return [], text
    end = text.find("\n---", 3)
    if end == -1:
        return [], text
    return text[4 : end + 1].splitlines(), text[end + 4 :].lstrip("\n")


def read_meta(text: str) -> dict[str, str]:
    """Extract the flat ``docs_*`` keys the sync owns from a note's frontmatter."""
    meta: dict[str, str] = {}
    for line in split_frontmatter(text)[0]:
        if not _DOCS_KEY.match(line):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta


def _yaml_scalar(value: str) -> str:
    """Quote a value only when leaving it bare would change its YAML meaning."""
    if value and value == value.strip() and not (_NEEDS_QUOTING & set(value)):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def compose(meta: dict[str, str], body: str, existing: str | None = None) -> str:
    """Build a note's full text, preserving frontmatter the user added themselves.

    The frontmatter is edited line by line rather than round-tripped through a
    YAML parser: the sync only ever writes flat ``docs_*`` scalars, and copying
    every other line verbatim keeps the user's comments, ordering and nested
    values intact — without adding a YAML dependency.
    """
    kept = [line for line in split_frontmatter(existing or "")[0] if not _DOCS_KEY.match(line)]
    lines = [f"{key}: {_yaml_scalar(value)}" for key, value in meta.items()] + kept
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body.strip() + "\n"


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` via a temporary file, so an interrupted run leaves no stub."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def resolve_within(root: Path, relative: str | Path) -> Path:
    """Resolve `relative` under `root`, refusing anything that escapes it.

    ``resolve()`` follows symlinks, so a link pointing outside the vault fails
    the containment check rather than slipping through it.
    """
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    if candidate != resolved_root and not candidate.is_relative_to(resolved_root):
        raise VaultPathError("path escapes the vault root")
    return candidate


def index_vault(root: Path) -> dict[str, Path]:
    """Map ``docs_id`` to file path for every synced note under `root`.

    Notes without a ``docs_id`` are the user's own and are never indexed, which
    is what keeps the sync from ever overwriting them. On the (user-made)
    duplicate, the first path in sorted order wins so the result is stable.
    """
    index: dict[str, Path] = {}
    if not root.exists():
        return index
    for path in sorted(root.rglob("*.md")):
        try:
            meta = read_meta(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        doc_id = meta.get("docs_id")
        if doc_id and doc_id not in index:
            index[doc_id] = path
    return index


def prune_empty_dirs(root: Path) -> None:
    """Remove directories left empty under `root` (deepest first). `root` itself stays."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_vault.py -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Commit**

```bash
git add src/mcp_docs/vault.py tests/test_vault.py
git commit -m "✨(vault) add filesystem layer for the Obsidian sync"
```

---

## Task 3: Découverte de l'arbre et disposition des fichiers

**Files:**
- Create: `src/mcp_docs/sync.py`
- Test: `tests/test_sync_layout.py`

**Interfaces:**
- Consumes: `DocsClient.list_all_children`, `DocsClient.get_document`, `vault.sanitize_name`.
- Produces: dataclass `TreeNode(id, title, updated_at, numchild, path, children)` ;
  `parse_document_ref(value) -> str` ; `discover_tree(client, root_id) -> TreeNode` ;
  `plan_layout(root) -> dict[str, PurePosixPath]` (chemins relatifs au dossier de destination,
  nom de la racine inclus).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sync_layout.py
"""Tree discovery and folder-note layout."""

from pathlib import PurePosixPath

import httpx
import pytest
import respx

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig
from mcp_docs.sync import TreeNode, discover_tree, parse_document_ref, plan_layout

BASE = "https://docs.example.org"


def node(doc_id, title, children=(), updated_at="2026-08-01T10:00:00Z", path=None):
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
    def test_extracts_uuid_from_url(self):
        url = "https://docs.numerique.gouv.fr/docs/5b243392-b3a5-4caa-a7e6-e88566e1c72e/"
        assert parse_document_ref(url) == "5b243392-b3a5-4caa-a7e6-e88566e1c72e"

    def test_accepts_a_bare_uuid_and_lowercases_it(self):
        assert parse_document_ref("5B243392-B3A5-4CAA-A7E6-E88566E1C72E") == (
            "5b243392-b3a5-4caa-a7e6-e88566e1c72e"
        )

    def test_rejects_a_value_without_uuid(self):
        with pytest.raises(ValueError):
            parse_document_ref("https://docs.numerique.gouv.fr/docs/")


class TestPlanLayout:
    def test_leaf_root_is_a_single_file(self):
        layout = plan_layout(node("r", "Racine"))
        assert layout == {"r": PurePosixPath("Racine.md")}

    def test_parent_becomes_a_folder_note(self):
        tree = node("r", "Racine", [node("a", "Enfant")])
        layout = plan_layout(tree)
        assert layout["r"] == PurePosixPath("Racine/Racine.md")
        assert layout["a"] == PurePosixPath("Racine/Enfant.md")

    def test_nested_parents_nest_folders(self):
        tree = node("r", "Racine", [node("a", "Enfant", [node("b", "Petit")])])
        layout = plan_layout(tree)
        assert layout["a"] == PurePosixPath("Racine/Enfant/Enfant.md")
        assert layout["b"] == PurePosixPath("Racine/Enfant/Petit.md")

    def test_titles_are_sanitized(self):
        tree = node("r", "Racine", [node("a", "Feedbacks / intérêt")])
        assert plan_layout(tree)["a"] == PurePosixPath("Racine/Feedbacks - intérêt.md")

    def test_sibling_collision_is_suffixed_by_materialized_path_order(self):
        tree = node(
            "r",
            "Racine",
            [node("a", "A/B", path="0000AAA2"), node("b", "A:B", path="0000AAA1")],
        )
        layout = plan_layout(tree)
        # "b" sorts first on its materialized path, so it keeps the bare name.
        assert layout["b"] == PurePosixPath("Racine/A-B.md")
        assert layout["a"] == PurePosixPath("Racine/A-B (2).md")

    def test_collision_resolution_is_stable_across_runs(self):
        tree = node(
            "r",
            "Racine",
            [node("a", "A/B", path="0000AAA2"), node("b", "A:B", path="0000AAA1")],
        )
        assert plan_layout(tree) == plan_layout(tree)

    def test_same_name_in_different_folders_does_not_collide(self):
        tree = node(
            "r",
            "Racine",
            [node("a", "Notes", [node("c", "Transcript")]), node("b", "Autres", [node("d", "Transcript")])],
        )
        layout = plan_layout(tree)
        assert layout["c"] == PurePosixPath("Racine/Notes/Transcript.md")
        assert layout["d"] == PurePosixPath("Racine/Autres/Transcript.md")


def _payload(doc_id, title, numchild=0, path="0000AAA"):
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
async def test_discover_tree_walks_every_level():
    respx.get(f"{BASE}/api/v1.0/documents/root/").mock(
        return_value=httpx.Response(200, json=_payload("root", "Racine", numchild=2))
    )
    respx.get(f"{BASE}/api/v1.0/documents/root/children/").mock(
        return_value=httpx.Response(
            200,
            json={"count": 2, "next": None, "previous": None,
                  "results": [_payload("a", "A", numchild=1, path="0000AAA1"),
                              _payload("b", "B", path="0000AAA2")]},
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/a/children/").mock(
        return_value=httpx.Response(
            200,
            json={"count": 1, "next": None, "previous": None,
                  "results": [_payload("c", "C", path="0000AAA10001")]},
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
async def test_discover_tree_does_not_fetch_children_of_leaves():
    respx.get(f"{BASE}/api/v1.0/documents/root/").mock(
        return_value=httpx.Response(200, json=_payload("root", "Racine"))
    )
    route = respx.get(f"{BASE}/api/v1.0/documents/root/children/").mock(
        return_value=httpx.Response(200, json={"count": 0, "next": None, "previous": None, "results": []})
    )
    client = DocsClient(DocsConfig(base_url=BASE, session_cookie="c"))
    try:
        tree = await discover_tree(client, "root")
    finally:
        await client.close()
    assert tree.children == []
    assert not route.called
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_sync_layout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_docs.sync'`

- [ ] **Step 3: Write the discovery and layout half of `src/mcp_docs/sync.py`**

```python
"""Engine for mirroring a Docs tree into an Obsidian vault.

Knows nothing about MCP: it takes a ``DocsClient`` and a vault root, and
returns a report. That is what keeps a future CLI a thin wrapper.
"""

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from mcp_docs.client import DocsClient
from mcp_docs.models import DocumentSummary
from mcp_docs.vault import sanitize_name

_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


@dataclass
class TreeNode:
    """One document in the tree being mirrored."""

    id: str
    title: str
    updated_at: str
    numchild: int
    path: str
    children: list["TreeNode"] = field(default_factory=list)


def parse_document_ref(value: str) -> str:
    """Extract a document UUID from a Docs URL or accept a bare UUID."""
    match = _UUID.search(value or "")
    if not match:
        raise ValueError("no document UUID found in the reference")
    return match.group(0).lower()


def _to_node(summary: DocumentSummary) -> TreeNode:
    return TreeNode(
        id=summary.id,
        title=summary.title or "",
        updated_at=summary.updated_at.isoformat() if summary.updated_at else "",
        numchild=summary.numchild,
        path=summary.path or summary.id,
    )


async def discover_tree(client: DocsClient, root_id: str) -> TreeNode:
    """Walk the subtree rooted at `root_id`, one level at a time.

    ``/tree/`` cannot be used: it returns the ancestor root with only the path
    to the requested document expanded. So we descend with ``/children/``,
    fanning out each level in parallel under the client's own semaphore, and
    skipping any node the server reports as childless.
    """
    root = _to_node(await client.get_document(root_id))
    level = [root]
    while level:
        parents = [node for node in level if node.numchild > 0]
        if not parents:
            return root
        results = await asyncio.gather(*(client.list_all_children(node.id) for node in parents))
        level = []
        for parent, children in zip(parents, results, strict=True):
            parent.children = [_to_node(child) for child in children]
            level.extend(parent.children)
    return root


def _assign_names(siblings: list[TreeNode]) -> dict[str, str]:
    """Give each sibling a file name unique within its folder.

    Sanitizing can map two distinct titles onto one name ("A/B" and "A:B" both
    become "A-B"). Siblings are ordered by their materialized path — stable
    server-side — so the same document keeps the same suffix across runs.
    Comparison is case-folded because macOS filesystems are case-insensitive.
    """
    names: dict[str, str] = {}
    taken: set[str] = set()
    for node in sorted(siblings, key=lambda item: item.path):
        base = sanitize_name(node.title)
        name = base
        suffix = 2
        while name.casefold() in taken:
            name = f"{base} ({suffix})"
            suffix += 1
        taken.add(name.casefold())
        names[node.id] = name
    return names


def plan_layout(root: TreeNode) -> dict[str, PurePosixPath]:
    """Map each document id to its path, relative to the destination folder.

    Folder-note convention: a document becomes a directory only when it has
    children, and then holds its own body in a note of the same name.
    """
    layout: dict[str, PurePosixPath] = {}

    def walk(node: TreeNode, parent_dir: PurePosixPath, name: str) -> None:
        if node.children:
            folder = parent_dir / name
            layout[node.id] = folder / f"{name}.md"
            child_names = _assign_names(node.children)
            for child in node.children:
                walk(child, folder, child_names[child.id])
        else:
            layout[node.id] = parent_dir / f"{name}.md"

    walk(root, PurePosixPath(), sanitize_name(root.title))
    return layout
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sync_layout.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/mcp_docs/sync.py tests/test_sync_layout.py
git commit -m "✨(sync) discover document trees and lay out folder notes"
```

---

## Task 4: Réécriture des liens en wikilinks

**Files:**
- Modify: `src/mcp_docs/sync.py`
- Test: `tests/test_sync_links.py`

**Interfaces:**
- Produces: `rewrite_links(markdown, base_url, names) -> str`, où `names` est
  `dict[str, str]` (uuid en minuscules → nom de fichier sans extension).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sync_links.py
"""Rewriting in-tree Docs links as Obsidian wikilinks."""

from mcp_docs.sync import rewrite_links

BASE = "https://docs.example.org"
NAMES = {"11111111-1111-4111-8111-111111111111": "🔮 Vision produit"}
OUT_OF_TREE = "22222222-2222-4222-8222-222222222222"


def test_markdown_link_keeps_its_text_as_an_alias():
    source = f"voir [la vision]({BASE}/docs/11111111-1111-4111-8111-111111111111/)"
    assert rewrite_links(source, BASE, NAMES) == "voir [[🔮 Vision produit|la vision]]"


def test_markdown_link_whose_text_is_the_target_name_drops_the_alias():
    source = f"[🔮 Vision produit]({BASE}/docs/11111111-1111-4111-8111-111111111111/)"
    assert rewrite_links(source, BASE, NAMES) == "[[🔮 Vision produit]]"


def test_bare_url_becomes_a_plain_wikilink():
    source = f"cf {BASE}/docs/11111111-1111-4111-8111-111111111111/ pour la suite"
    assert rewrite_links(source, BASE, NAMES) == "cf [[🔮 Vision produit]] pour la suite"


def test_url_without_trailing_slash_is_matched():
    source = f"{BASE}/docs/11111111-1111-4111-8111-111111111111"
    assert rewrite_links(source, BASE, NAMES) == "[[🔮 Vision produit]]"


def test_uppercase_uuid_is_matched():
    source = f"{BASE}/docs/11111111-1111-4111-8111-111111111111".upper().replace(
        BASE.upper(), BASE
    )
    assert rewrite_links(source, BASE, NAMES) == "[[🔮 Vision produit]]"


def test_link_outside_the_tree_is_left_alone():
    source = f"[ailleurs]({BASE}/docs/{OUT_OF_TREE}/)"
    assert rewrite_links(source, BASE, NAMES) == source


def test_media_url_is_left_alone():
    source = f"![img]({BASE}/media/abc/attachments/def.png)"
    assert rewrite_links(source, BASE, NAMES) == source


def test_trailing_slash_on_base_url_is_tolerated():
    source = f"{BASE}/docs/11111111-1111-4111-8111-111111111111/"
    assert rewrite_links(source, BASE + "/", NAMES) == "[[🔮 Vision produit]]"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_sync_links.py -v`
Expected: FAIL — `ImportError: cannot import name 'rewrite_links'`

- [ ] **Step 3: Add `rewrite_links` to `src/mcp_docs/sync.py`**

Ajouter après `plan_layout` :

```python
def rewrite_links(markdown: str, base_url: str, names: dict[str, str]) -> str:
    """Turn links to documents inside the synced tree into Obsidian wikilinks.

    Obsidian resolves ``[[name]]`` by file name wherever the note lives, so the
    mirror stays navigable without embedding relative paths that would break on
    every move. Links to documents outside the tree, and ``/media/`` URLs, are
    left untouched — they still need the browser and its session.
    """
    prefix = re.escape(base_url.rstrip("/"))
    document_url = rf"{prefix}/docs/({_UUID.pattern})/?"

    def as_markdown_link(match: re.Match[str]) -> str:
        text, doc_id = match.group(1), match.group(2).lower()
        name = names.get(doc_id)
        if name is None:
            return match.group(0)
        return f"[[{name}]]" if text.strip() in ("", name) else f"[[{name}|{text}]]"

    def as_bare_link(match: re.Match[str]) -> str:
        name = names.get(match.group(1).lower())
        return f"[[{name}]]" if name else match.group(0)

    markdown = re.sub(rf"\[([^\]]*)\]\({document_url}\)", as_markdown_link, markdown)
    return re.sub(document_url, as_bare_link, markdown)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sync_links.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/mcp_docs/sync.py tests/test_sync_links.py
git commit -m "✨(sync) rewrite in-tree document links as wikilinks"
```

---

## Task 5: Classement, écriture et rapport

**Files:**
- Modify: `src/mcp_docs/sync.py`
- Test: `tests/test_sync_engine.py`

**Interfaces:**
- Consumes: `TreeNode`, `discover_tree`, `plan_layout`, `rewrite_links`, toute la couche `vault`.
- Produces: dataclasses `Change(action, doc_id, title, path, from_path)` et
  `SyncReport(root_title, destination, dry_run, scanned, created, updated, moved, unchanged,
  changes, changes_truncated, orphans, errors)` ;
  `async sync_tree(client, *, vault_root, destination, document, dry_run) -> SyncReport`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sync_engine.py
"""End-to-end behaviour of the sync engine against a mocked API and a temp vault."""

import httpx
import pytest
import respx

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig
from mcp_docs.sync import sync_tree
from mcp_docs.vault import read_meta

BASE = "https://docs.example.org"
ROOT = "5b243392-b3a5-4caa-a7e6-e88566e1c72e"
CHILD = "11111111-1111-4111-8111-111111111111"


def _doc(doc_id, title, updated_at, numchild=0, path="0000AAA"):
    return {
        "id": doc_id,
        "title": title,
        "updated_at": updated_at,
        "numchild": numchild,
        "path": path,
        "depth": 1,
    }


def _mock_tree(root_updated="2026-08-01T10:00:00Z", child_updated="2026-08-02T10:00:00Z",
               root_title="Racine", child_title="Enfant", child_body="corps enfant"):
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/").mock(
        return_value=httpx.Response(200, json=_doc(ROOT, root_title, root_updated, numchild=1))
    )
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/children/").mock(
        return_value=httpx.Response(
            200,
            json={"count": 1, "next": None, "previous": None,
                  "results": [_doc(CHILD, child_title, child_updated, path="0000AAA0001")]},
        )
    )
    root_content = respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/formatted-content/").mock(
        return_value=httpx.Response(
            200, json={"id": ROOT, "title": root_title, "content": "corps racine",
                       "updated_at": root_updated}
        )
    )
    child_content = respx.get(f"{BASE}/api/v1.0/documents/{CHILD}/formatted-content/").mock(
        return_value=httpx.Response(
            200, json={"id": CHILD, "title": child_title, "content": child_body,
                       "updated_at": child_updated}
        )
    )
    return root_content, child_content


async def _run(vault, dry_run=False, destination="Docs"):
    client = DocsClient(DocsConfig(base_url=BASE, session_cookie="c"))
    try:
        return await sync_tree(
            client, vault_root=vault, destination=destination,
            document=f"{BASE}/docs/{ROOT}/", dry_run=dry_run,
        )
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_first_sync_creates_the_whole_tree(tmp_path):
    _mock_tree()
    report = await _run(tmp_path)

    root_note = tmp_path / "Docs" / "Racine" / "Racine.md"
    child_note = tmp_path / "Docs" / "Racine" / "Enfant.md"
    assert root_note.read_text(encoding="utf-8").endswith("corps racine\n")
    assert child_note.exists()
    assert report.created == 2
    assert report.scanned == 2
    assert read_meta(root_note.read_text(encoding="utf-8"))["docs_id"] == ROOT
    assert read_meta(root_note.read_text(encoding="utf-8"))["docs_url"] == f"{BASE}/docs/{ROOT}/"


@pytest.mark.asyncio
@respx.mock
async def test_second_sync_without_upstream_change_downloads_nothing(tmp_path):
    _mock_tree()
    await _run(tmp_path)
    root_content, child_content = _mock_tree()
    report = await _run(tmp_path)

    assert report.unchanged == 2
    assert report.updated == 0
    assert not root_content.called
    assert not child_content.called


@pytest.mark.asyncio
@respx.mock
async def test_only_the_changed_document_is_downloaded(tmp_path):
    _mock_tree()
    await _run(tmp_path)
    root_content, child_content = _mock_tree(child_updated="2026-08-09T10:00:00Z",
                                             child_body="corps modifié")
    report = await _run(tmp_path)

    assert report.updated == 1
    assert report.unchanged == 1
    assert not root_content.called
    assert child_content.called
    child_note = tmp_path / "Docs" / "Racine" / "Enfant.md"
    assert child_note.read_text(encoding="utf-8").endswith("corps modifié\n")


@pytest.mark.asyncio
@respx.mock
async def test_leaf_becoming_a_parent_moves_its_note(tmp_path):
    _mock_tree()
    await _run(tmp_path)
    grandchild = "33333333-3333-4333-8333-333333333333"
    _mock_tree()
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/children/").mock(
        return_value=httpx.Response(
            200,
            json={"count": 1, "next": None, "previous": None,
                  "results": [_doc(CHILD, "Enfant", "2026-08-02T10:00:00Z", numchild=1,
                                   path="0000AAA0001")]},
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/{CHILD}/children/").mock(
        return_value=httpx.Response(
            200,
            json={"count": 1, "next": None, "previous": None,
                  "results": [_doc(grandchild, "Petit", "2026-08-03T10:00:00Z",
                                   path="0000AAA00010001")]},
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/{grandchild}/formatted-content/").mock(
        return_value=httpx.Response(
            200, json={"id": grandchild, "title": "Petit", "content": "corps petit",
                       "updated_at": "2026-08-03T10:00:00Z"}
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
async def test_renamed_document_moves_and_is_reported_with_its_origin(tmp_path):
    _mock_tree()
    await _run(tmp_path)
    _mock_tree(child_title="Enfant renommé")
    report = await _run(tmp_path)

    assert not (tmp_path / "Docs" / "Racine" / "Enfant.md").exists()
    assert (tmp_path / "Docs" / "Racine" / "Enfant renommé.md").exists()
    assert report.moved == 1
    entry = next(change for change in report.changes if change.action == "moved")
    assert entry.from_path.endswith("Enfant.md")


@pytest.mark.asyncio
@respx.mock
async def test_orphan_is_reported_and_left_untouched(tmp_path):
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
async def test_personal_notes_are_never_touched(tmp_path):
    _mock_tree()
    personal = tmp_path / "Docs" / "Racine"
    personal.mkdir(parents=True)
    (personal / "Mes idées.md").write_text("---\ntags: [x]\n---\n\nà moi\n", encoding="utf-8")
    report = await _run(tmp_path)

    assert (personal / "Mes idées.md").read_text(encoding="utf-8") == "---\ntags: [x]\n---\n\nà moi\n"
    assert report.orphans == []


@pytest.mark.asyncio
@respx.mock
async def test_user_frontmatter_survives_an_update(tmp_path):
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
async def test_dry_run_writes_nothing_and_downloads_no_content(tmp_path):
    root_content, child_content = _mock_tree()
    report = await _run(tmp_path, dry_run=True)

    assert report.dry_run is True
    assert report.created == 2
    assert not (tmp_path / "Docs").exists()
    assert not root_content.called
    assert not child_content.called


@pytest.mark.asyncio
@respx.mock
async def test_a_failing_document_does_not_abort_the_others(tmp_path):
    _mock_tree()
    respx.get(f"{BASE}/api/v1.0/documents/{CHILD}/formatted-content/").mock(
        return_value=httpx.Response(500, json={})
    )
    report = await _run(tmp_path)

    assert (tmp_path / "Docs" / "Racine" / "Racine.md").exists()
    assert len(report.errors) == 1
    assert CHILD in report.errors[0]["document_id"]


@pytest.mark.asyncio
@respx.mock
async def test_in_tree_links_are_rewritten_on_write(tmp_path):
    _mock_tree(child_body=f"voir [la racine]({BASE}/docs/{ROOT}/)")
    await _run(tmp_path)

    child_note = tmp_path / "Docs" / "Racine" / "Enfant.md"
    assert "[[Racine|la racine]]" in child_note.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_sync_engine.py -v`
Expected: FAIL — `ImportError: cannot import name 'sync_tree'`

- [ ] **Step 3: Add the engine to `src/mcp_docs/sync.py`**

Compléter les imports en tête du module :

```python
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from mcp_docs.client import DocsClient
from mcp_docs.exceptions import DocsAPIError
from mcp_docs.models import DocumentSummary
from mcp_docs.vault import (
    compose,
    index_vault,
    prune_empty_dirs,
    read_meta,
    resolve_within,
    sanitize_name,
    write_atomic,
)

logger = logging.getLogger(__name__)

_MAX_REPORTED_CHANGES = 50
```

Puis ajouter en fin de module :

```python
@dataclass
class Change:
    """One file-level effect of a sync run."""

    action: str  # created | updated | moved | unchanged
    doc_id: str
    title: str
    path: str
    from_path: str | None = None


@dataclass
class SyncReport:
    """Outcome of a sync run, shaped to be read by an LLM without flooding it."""

    root_title: str = ""
    destination: str = ""
    dry_run: bool = False
    scanned: int = 0
    created: int = 0
    updated: int = 0
    moved: int = 0
    unchanged: int = 0
    changes: list[Change] = field(default_factory=list)
    changes_truncated: bool = False
    orphans: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def _document_url(base_url: str, doc_id: str) -> str:
    return f"{base_url.rstrip('/')}/docs/{doc_id}/"


def _flatten(node: TreeNode) -> list[TreeNode]:
    return [node] + [item for child in node.children for item in _flatten(child)]


async def sync_tree(
    client: DocsClient,
    *,
    vault_root: Path,
    destination: str,
    document: str,
    dry_run: bool = False,
) -> SyncReport:
    """Mirror the tree rooted at `document` into `vault_root / destination`.

    Discovery never downloads content: the decision to re-fetch a document is
    taken by comparing the server's ``updated_at`` with the one recorded in the
    local note's frontmatter. Only documents that actually moved are read.
    """
    root_id = parse_document_ref(document)
    tree = await discover_tree(client, root_id)
    layout = plan_layout(tree)
    nodes = {node.id: node for node in _flatten(tree)}
    names = {doc_id: path.stem for doc_id, path in layout.items()}

    destination_dir = resolve_within(vault_root, destination)
    index = index_vault(destination_dir)

    root_folder = resolve_within(destination_dir, layout[tree.id]).parent
    report = SyncReport(
        root_title=tree.title,
        destination=str(root_folder.relative_to(vault_root.resolve())),
        dry_run=dry_run,
        scanned=len(nodes),
    )

    to_write: list[tuple[TreeNode, Path, Path | None, str]] = []
    for doc_id, relative in layout.items():
        node = nodes[doc_id]
        target = resolve_within(destination_dir, relative)
        current = index.get(doc_id)
        moved = current is not None and current != target
        stale = current is None or _recorded_updated_at(current) != node.updated_at

        if current is None:
            action = "created"
            report.created += 1
        elif moved:
            action = "moved"
            report.moved += 1
        elif stale:
            action = "updated"
            report.updated += 1
        else:
            report.unchanged += 1
            continue

        _record(report, Change(
            action=action,
            doc_id=doc_id,
            title=node.title,
            path=str(target.relative_to(vault_root.resolve())),
            from_path=str(current.relative_to(vault_root.resolve())) if moved else None,
        ))
        to_write.append((node, target, current, "skip" if (moved and not stale) else "fetch"))

    for doc_id, path in index.items():
        if doc_id not in layout:
            report.orphans.append({
                "document_id": doc_id,
                "title": path.stem,
                "path": str(path.relative_to(vault_root.resolve())),
            })

    if dry_run:
        return report

    await asyncio.gather(*(
        _apply(client, report, node, target, current, mode, names)
        for node, target, current, mode in to_write
    ))
    prune_empty_dirs(destination_dir)
    return report


def _record(report: SyncReport, change: Change) -> None:
    """Append a change, capping the list so the report stays small."""
    if len(report.changes) < _MAX_REPORTED_CHANGES:
        report.changes.append(change)
    else:
        report.changes_truncated = True


def _recorded_updated_at(path: Path) -> str | None:
    """Read the ``docs_updated_at`` the last sync wrote into a note."""
    try:
        return read_meta(path.read_text(encoding="utf-8")).get("docs_updated_at")
    except (OSError, UnicodeDecodeError):
        return None


async def _apply(
    client: DocsClient,
    report: SyncReport,
    node: TreeNode,
    target: Path,
    current: Path | None,
    mode: str,
    names: dict[str, str],
) -> None:
    """Write one document to disk, moving its previous file when it exists.

    A failure here is recorded and swallowed: one unreadable document must not
    cost the whole run.
    """
    existing = ""
    try:
        if current is not None and current != target:
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = current.read_text(encoding="utf-8")
            current.replace(target)
        elif target.exists():
            existing = target.read_text(encoding="utf-8")

        if mode == "skip":
            return

        content = await client.get_document_content(node.id, "markdown")
        body = rewrite_links(content.content or "", str(client.base_url), names)
        meta = {
            "docs_id": node.id,
            "docs_url": _document_url(str(client.base_url), node.id),
            "docs_title": node.title,
            "docs_updated_at": node.updated_at,
            "docs_synced_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        write_atomic(target, compose(meta, body, existing=existing or None))
    except (DocsAPIError, OSError) as error:
        logger.warning("Sync failed for document %s: %s", node.id, error)
        report.errors.append({
            "document_id": node.id,
            "title": node.title,
            "reason": type(error).__name__,
        })
```

`DocsClient` doit exposer son URL de base au moteur. Ajouter dans `src/mcp_docs/client.py`,
après `_reload_session_cookie` :

```python
    @property
    def base_url(self) -> httpx.URL:
        """Base URL of the Docs instance, needed to build and match document links."""
        return self._client.base_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sync_engine.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest`
Expected: PASS, aucune régression sur les tests existants.

- [ ] **Step 6: Commit**

```bash
git add src/mcp_docs/sync.py src/mcp_docs/client.py tests/test_sync_engine.py
git commit -m "✨(sync) classify, write and report a tree synchronisation"
```

---

## Task 6: Tool MCP `docs_sync_tree`

**Files:**
- Create: `src/mcp_docs/tools_sync.py`
- Modify: `src/mcp_docs/server.py`
- Modify: `CLAUDE.md`, `README.md`
- Test: `tests/test_tools_sync.py`

**Interfaces:**
- Consumes: `sync_tree`, `SyncReport`, `DocsConfig.vault_path`, `VaultPathError`.
- Produces: tool MCP `docs_sync_tree(document, destination="Docs", dry_run=False) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tools_sync.py
"""MCP tool wrapping the vault sync engine."""

import json

import httpx
import pytest
import respx

from mcp_docs.tools_sync import docs_sync_tree

BASE = "https://docs.example.org"
ROOT = "5b243392-b3a5-4caa-a7e6-e88566e1c72e"


def _mock_single_document():
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/").mock(
        return_value=httpx.Response(
            200,
            json={"id": ROOT, "title": "Racine", "updated_at": "2026-08-01T10:00:00Z",
                  "numchild": 0, "path": "0000AAA", "depth": 1},
        )
    )
    respx.get(f"{BASE}/api/v1.0/documents/{ROOT}/formatted-content/").mock(
        return_value=httpx.Response(
            200, json={"id": ROOT, "title": "Racine", "content": "corps",
                       "updated_at": "2026-08-01T10:00:00Z"}
        )
    )


@pytest.mark.asyncio
async def test_refuses_when_vault_path_is_not_configured(mock_context_no_vault):
    result = await docs_sync_tree(mock_context_no_vault, document=f"{BASE}/docs/{ROOT}/")
    assert "DOCS_VAULT_PATH" in result


@pytest.mark.asyncio
async def test_rejects_an_empty_document_reference(mock_context):
    assert "Error" in await docs_sync_tree(mock_context, document="  ")


@pytest.mark.asyncio
async def test_rejects_a_reference_without_uuid(mock_context):
    result = await docs_sync_tree(mock_context, document="https://docs.example.org/docs/")
    assert "Error" in result


@pytest.mark.asyncio
async def test_rejects_an_absolute_destination(mock_context):
    result = await docs_sync_tree(mock_context, document=ROOT, destination="/etc")
    assert "Error" in result


@pytest.mark.asyncio
async def test_rejects_a_traversing_destination(mock_context):
    result = await docs_sync_tree(mock_context, document=ROOT, destination="../../etc")
    assert "Error" in result


@pytest.mark.asyncio
@respx.mock
async def test_returns_a_json_report(mock_context, vault_dir):
    _mock_single_document()
    payload = json.loads(await docs_sync_tree(mock_context, document=f"{BASE}/docs/{ROOT}/"))

    assert payload["root"] == "Racine"
    assert payload["created"] == 1
    assert payload["scanned"] == 1
    assert (vault_dir / "Docs" / "Racine.md").exists()


@pytest.mark.asyncio
@respx.mock
async def test_dry_run_reports_without_writing(mock_context, vault_dir):
    _mock_single_document()
    payload = json.loads(
        await docs_sync_tree(mock_context, document=f"{BASE}/docs/{ROOT}/", dry_run=True)
    )

    assert payload["dry_run"] is True
    assert payload["created"] == 1
    assert not (vault_dir / "Docs").exists()
```

Et les fixtures locales, en tête de `tests/test_tools_sync.py`, sur le modèle exact des autres
fichiers de tests de tools (`tests/test_tools.py:45`) — `MagicMock` + `AppContext`, rien à
ajouter dans `conftest.py` :

```python
from unittest.mock import MagicMock

from mcp_docs.app import AppContext
from mcp_docs.client import DocsClient

from .conftest import make_config


@pytest.fixture
def vault_dir(tmp_path):
    """A vault root for sync tests."""
    root = tmp_path / "vault"
    root.mkdir()
    return root


@pytest.fixture
def mock_context(vault_dir) -> MagicMock:
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_tools_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_docs.tools_sync'`

- [ ] **Step 3: Write `src/mcp_docs/tools_sync.py`**

```python
"""MCP tool mirroring a Docs tree into a local Obsidian vault."""

import json
import logging
from dataclasses import asdict
from pathlib import PurePosixPath

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from mcp_docs.app import AppContext, mcp
from mcp_docs.exceptions import DocsAPIError, DocsAuthError, DocsNotFoundError, DocsPermissionError
from mcp_docs.sync import SyncReport, sync_tree
from mcp_docs.vault import VaultPathError

logger = logging.getLogger(__name__)


def _error_response(err: DocsAPIError) -> str:
    logger.warning("API error: HTTP %d — %s", err.status_code, err.message)
    if isinstance(err, DocsAuthError):
        return "Authentication failed. Please check your credentials."
    if isinstance(err, DocsPermissionError):
        return "Access denied. You don't have permission to perform this action."
    if isinstance(err, DocsNotFoundError):
        return "Document not found."
    return f"Request failed (HTTP {err.status_code})."


def _as_payload(report: SyncReport) -> str:
    return json.dumps(
        {
            "root": report.root_title,
            "destination": report.destination,
            "dry_run": report.dry_run,
            "scanned": report.scanned,
            "created": report.created,
            "updated": report.updated,
            "moved": report.moved,
            "unchanged": report.unchanged,
            "changes": [asdict(change) for change in report.changes],
            "changes_truncated": report.changes_truncated,
            "orphans": report.orphans,
            "errors": report.errors,
        },
        ensure_ascii=False,
    )


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_sync_tree(
    ctx: Context,
    document: str,
    destination: str = "Docs",
    dry_run: bool = False,
) -> str:
    """Mirror a Docs document and all its sub-documents into the local Obsidian vault.

    Downloads only the documents whose server-side ``updated_at`` differs from
    the one recorded in the local note, so a routine run is cheap. Documents are
    written as folder notes: a document becomes a directory only when it has
    children. Files that are no longer in the tree are reported as orphans and
    never deleted. Images are left as authenticated URLs and will not render.

    Args:
        document: Docs URL of the parent document, or its UUID.
        destination: Parent folder inside the vault. The tree is written to
            ``<destination>/<root title>/``. Defaults to "Docs".
        dry_run: Report what would change without downloading or writing anything.
    """
    if not document or not document.strip():
        return "Error: document is required (a Docs URL or a document UUID)."

    app_ctx: AppContext = ctx.request_context.lifespan_context
    vault_root = app_ctx.config.vault_path
    if vault_root is None:
        return (
            "Error: vault sync is disabled. Set DOCS_VAULT_PATH to the absolute path "
            "of your Obsidian vault in the MCP server environment, then restart it."
        )
    if not vault_root.is_dir():
        return "Error: DOCS_VAULT_PATH does not point to an existing directory."

    candidate = PurePosixPath(destination.strip() or "Docs")
    if candidate.is_absolute() or ".." in candidate.parts:
        return "Error: destination must be a relative path inside the vault, without '..'."

    try:
        report = await sync_tree(
            app_ctx.client,
            vault_root=vault_root,
            destination=str(candidate),
            document=document.strip(),
            dry_run=dry_run,
        )
    except ValueError as error:
        if isinstance(error, VaultPathError):
            return "Error: the computed path would fall outside the vault."
        logger.warning("Invalid sync reference: %s", error)
        return "Error: could not find a document UUID in the given reference."
    except DocsAPIError as error:
        return _error_response(error)

    return _as_payload(report)
```

- [ ] **Step 4: Register the module**

Dans `src/mcp_docs/server.py`, après la ligne `import mcp_docs.tools_sharing` (ligne 12) :

```python
import mcp_docs.tools_sync  # noqa: F401 — registers the Obsidian vault sync tool
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools_sync.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Document the tool**

Dans `CLAUDE.md`, ajouter la ligne au tableau « Tools MCP » :

```markdown
| `docs_sync_tree` | Miroir d'un arbre de documents vers un vault Obsidian | P1 | ✅ |
```

et dans la section « Configuration », après `DOCS_SESSION_FILE` :

```markdown
# Racine du vault Obsidian — active docs_sync_tree (aucune écriture hors de ce dossier)
DOCS_VAULT_PATH=/chemin/vers/le/vault
```

Dans `README.md`, ajouter une section « Synchronisation vers Obsidian » décrivant :
la variable `DOCS_VAULT_PATH`, l'appel `docs_sync_tree`, la convention folder note, le fait
que les orphelins sont signalés et jamais supprimés, et que les images restent des URLs
authentifiées.

- [ ] **Step 7: Full verification**

```bash
uv run pytest && uv run ruff check . && uv run pyright
```

Expected: suite verte, aucun diagnostic ruff, aucune erreur pyright.

- [ ] **Step 8: Commit**

```bash
git add src/mcp_docs/tools_sync.py src/mcp_docs/server.py tests/test_tools_sync.py tests/conftest.py CLAUDE.md README.md
git commit -m "✨(tools) add docs_sync_tree to mirror a document tree into a vault"
```

---

## Task 7: Essai réel en dry-run sur l'arbre Hub

- [ ] **Step 1: Point the server at the vault**

Vérifier que `DOCS_VAULT_PATH=/Users/dinum-327779/Documents/LaSuite` est présent dans la config
MCP du serveur `docs`, et redémarrer le serveur pour qu'il le lise.

- [ ] **Step 2: Dry-run on the Hub tree**

Appeler `docs_sync_tree` avec
`document="https://docs.numerique.gouv.fr/docs/5b243392-b3a5-4caa-a7e6-e88566e1c72e/"` et
`dry_run=True`.

Attendu : `scanned` ≈ 129, `created` ≈ 129, `errors` vide, aucun fichier écrit dans le vault.

- [ ] **Step 3: Present the plan to Louis and wait**

Aucune écriture réelle avant validation explicite du plan affiché.

- [ ] **Step 4: Real run, then second run**

Après accord : `dry_run=False`, puis relancer immédiatement. Le second passage doit afficher
`unchanged` ≈ 129, `updated: 0`, et n'écrire aucun fichier.

- [ ] **Step 5: Record lessons**

Consigner dans `tasks/lessons.md` tout écart entre le comportement observé et la spec.

---

## Résultat

Livré le 2026-08-14. 8 commits, **256 tests verts**, ruff propre, pyright propre sur le code
ajouté.

| Module | Rôle |
|--------|------|
| `src/mcp_docs/sync.py` | Découverte récursive, disposition folder note, classement, écriture, wikilinks |
| `src/mcp_docs/vault.py` | Nommage, frontmatter ligne à ligne, écriture atomique, garde-fou de chemin |
| `src/mcp_docs/tools_sync.py` | Tool MCP `docs_sync_tree` |

### Vérification sur l'arbre réel (Hub, 129 documents, profondeur 5)

```
dry-run    : 129 parcourus, 129 créés, 0 erreur, 7,4 s — rien écrit
passage 1  : 129 fichiers écrits, 0 erreur, 16,0 s
passage 2  : 129 inchangés, 0 création, 0 écriture, 9,6 s → idempotent
```

Confinement vérifié après écriture : seuls les 129 fichiers sous `Docs/` ont été créés. Hors
`Docs/`, un seul fichier a changé — `.obsidian/workspace.json`, réécrit par Obsidian lui-même
en réindexant.

### Écarts par rapport au plan

- Deux tests écrits avec `route.called` échouaient à tort : respx réutilise l'objet `Route`
  d'un motif déjà enregistré. Corrigés en comparant des deltas de `call_count`.
- `resolve_within` a dû accepter `PurePath` et non `str | Path` : `plan_layout` produit des
  `PurePosixPath`.
- Le second passage a d'abord échoué sur un `429` — deux arbres complets enchaînés dépassent
  le plafond de l'API. Voir `lessons.md`.

### Reste à faire

- Ajouter `DOCS_VAULT_PATH` à `claude_desktop_config.json` et redémarrer l'app, pour que le
  tool soit appelable depuis une conversation.
- Corriger l'erreur pyright préexistante de `session_refresh.py:114` (hors périmètre, mais
  bloque la CI et donc la PR).
- Ouvrir la PR.
