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
    """Return a safe error message without leaking internal details."""
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

    Only documents whose server-side update time differs from the one recorded in
    the local note are downloaded, so a routine run is cheap. A document that is
    already mirrored somewhere in the vault is refreshed where it lives, even if
    that is inside a larger tree synced earlier — syncing one document never
    clones a copy it already has. Notes are written as folder notes: a document
    becomes a directory only when it has children. Files no longer part of the
    tree are reported as orphans and never deleted, notes without a docs_id are
    never touched, and images stay as authenticated URLs that will not render.

    Args:
        document: Docs URL of the parent document, or its UUID.
        destination: Where documents that have no note yet are created. The tree
            goes to "<destination>/<root title>/". Defaults to "Docs".
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
    except VaultPathError:
        return "Error: the computed path would fall outside the vault."
    except ValueError as error:
        logger.warning("Invalid sync reference: %s", error)
        return "Error: could not find a document UUID in the given reference."
    except DocsAPIError as error:
        return _error_response(error)

    return _as_payload(report)
