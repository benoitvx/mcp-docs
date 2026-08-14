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
    """Cut ``value`` to ``limit`` UTF-8 bytes without splitting a character."""
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def sanitize_name(title: str) -> str:
    """Turn a document title into a file name that is safe on macOS and legible.

    Emoji are kept on purpose: they carry meaning in this vault, and both the
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
    """Write ``text`` to ``path`` via a temp file, so an interrupted run leaves no stub."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def resolve_within(root: Path, relative: str | Path) -> Path:
    """Resolve ``relative`` under ``root``, refusing anything that escapes it.

    ``resolve()`` follows symlinks, so a link pointing outside the vault fails
    the containment check rather than slipping through it.
    """
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    if candidate != resolved_root and not candidate.is_relative_to(resolved_root):
        raise VaultPathError("path escapes the vault root")
    return candidate


def index_vault(root: Path) -> dict[str, Path]:
    """Map ``docs_id`` to file path for every synced note under ``root``.

    Notes without a ``docs_id`` are the user's own and are never indexed, which
    is what keeps the sync from ever overwriting them. Should the user duplicate
    a note, the first path in sorted order wins so the result stays stable.
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
    """Remove directories left empty under ``root`` (deepest first). ``root`` itself stays."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
