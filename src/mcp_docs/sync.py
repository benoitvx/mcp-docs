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

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


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
