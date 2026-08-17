"""Engine for mirroring a Docs tree into an Obsidian vault.

Knows nothing about MCP: it takes a ``DocsClient`` and a vault root, and
returns a report. That is what keeps a future CLI a thin wrapper.
"""

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

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_MAX_REPORTED_CHANGES = 50


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
    """Extract a document UUID from a Docs URL, or accept a bare UUID."""
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
    """Walk the subtree rooted at ``root_id``, one level at a time.

    ``/tree/`` cannot be used: it returns the ancestor root with only the path
    to the requested document expanded, siblings arriving collapsed. So we
    descend with ``/children/``, fanning out each level in parallel under the
    client's own semaphore, and skipping any node the server reports as
    childless. No document content is fetched here.
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
    server-side — so a document keeps the same suffix across runs. Comparison is
    case-folded because macOS filesystems are case-insensitive.
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


@dataclass
class Change:
    """One file-level effect of a sync run."""

    action: str  # created | updated | moved
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


def _record(report: SyncReport, change: Change) -> None:
    """Append a change, capping the list so the report stays small."""
    if len(report.changes) < _MAX_REPORTED_CHANGES:
        report.changes.append(change)
    else:
        report.changes_truncated = True


def _owned_folder(
    destination_dir: Path, tree: TreeNode, layout: dict[str, PurePosixPath]
) -> Path | None:
    """The directory this run lays its tree out in, or None when it writes a single file.

    Only notes under this folder are considered part of the mirror being written:
    they follow the layout (so renames and reparenting move them), and they are
    the only ones that can be reported as orphans. A childless root owns no
    folder — it would otherwise claim the whole destination.
    """
    if not tree.children:
        return None
    return resolve_within(destination_dir, layout[tree.id]).parent


def _target_for(
    current: Path | None,
    destination_dir: Path,
    relative: PurePosixPath,
    owned: Path | None,
) -> Path:
    """Where a document's note belongs: in place if it already lives outside this run."""
    if current is not None and (owned is None or not current.is_relative_to(owned)):
        return current
    return resolve_within(destination_dir, relative)


def _recorded_updated_at(path: Path) -> str | None:
    """Read the ``docs_updated_at`` the last sync wrote into a note."""
    try:
        return read_meta(path.read_text(encoding="utf-8")).get("docs_updated_at")
    except (OSError, UnicodeDecodeError):
        return None


async def sync_tree(
    client: DocsClient,
    *,
    vault_root: Path,
    destination: str,
    document: str,
    dry_run: bool = False,
) -> SyncReport:
    """Mirror the tree rooted at ``document`` into the vault.

    Discovery never downloads content: whether a document must be re-fetched is
    decided by comparing the server's ``updated_at`` with the one recorded in
    the local note's frontmatter. Only documents that actually moved are read.

    ``destination`` decides where documents that have *no* note yet are created.
    A document already mirrored somewhere else in the vault is refreshed where it
    lives, so asking to sync one document does not clone the copy it already has
    inside a larger tree.
    """
    root_id = parse_document_ref(document)
    tree = await discover_tree(client, root_id)
    layout = plan_layout(tree)
    nodes = {node.id: node for node in _flatten(tree)}
    names = {doc_id: path.stem for doc_id, path in layout.items()}

    vault = vault_root.resolve()
    destination_dir = resolve_within(vault, destination)
    index = index_vault(vault)
    owned = _owned_folder(destination_dir, tree, layout)
    targets = {
        doc_id: _target_for(index.get(doc_id), destination_dir, relative, owned)
        for doc_id, relative in layout.items()
    }

    report = SyncReport(
        root_title=tree.title,
        destination=str(targets[tree.id].parent.relative_to(vault)),
        dry_run=dry_run,
        scanned=len(nodes),
    )

    pending: list[tuple[TreeNode, Path, Path | None, bool]] = []
    for doc_id, target in targets.items():
        node = nodes[doc_id]
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

        _record(
            report,
            Change(
                action=action,
                doc_id=doc_id,
                title=node.title,
                path=str(target.relative_to(vault)),
                from_path=str(current.relative_to(vault)) if moved and current else None,
            ),
        )
        pending.append((node, target, current, stale))

    # Orphans are only meaningful inside the folder this run owns; notes belonging
    # to another mirror elsewhere in the vault are none of this run's business.
    if owned is not None:
        for doc_id, path in index.items():
            if doc_id not in layout and path.is_relative_to(owned):
                report.orphans.append(
                    {
                        "document_id": doc_id,
                        "title": path.stem,
                        "path": str(path.relative_to(vault)),
                    }
                )

    if dry_run:
        return report

    await asyncio.gather(
        *(
            _apply(client, report, node, target, current, stale, names)
            for node, target, current, stale in pending
        )
    )
    prune_empty_dirs(destination_dir)
    return report


async def _apply(
    client: DocsClient,
    report: SyncReport,
    node: TreeNode,
    target: Path,
    current: Path | None,
    stale: bool,
    names: dict[str, str],
) -> None:
    """Write one document to disk, moving its previous file when there is one.

    A failure here is recorded and swallowed: one unreadable document must not
    cost the whole run.
    """
    try:
        existing = ""
        if current is not None and current != target:
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = current.read_text(encoding="utf-8")
            current.replace(target)
        elif target.exists():
            existing = target.read_text(encoding="utf-8")

        if not stale:
            return

        base_url = str(client.base_url)
        content = await client.get_document_content(node.id, "markdown")
        body = rewrite_links(content.content or "", base_url, names)
        meta = {
            "docs_id": node.id,
            "docs_url": _document_url(base_url, node.id),
            "docs_title": node.title,
            "docs_updated_at": node.updated_at,
            "docs_synced_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        write_atomic(target, compose(meta, body, existing=existing or None))
    except (DocsAPIError, OSError) as error:
        logger.warning("Sync failed for document %s: %s", node.id, error)
        report.errors.append(
            {"document_id": node.id, "title": node.title, "reason": type(error).__name__}
        )
