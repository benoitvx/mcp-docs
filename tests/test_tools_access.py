"""Tests for access and invitation MCP tools."""

import json
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from mcp_docs.app import AppContext
from mcp_docs.client import DocsClient
from mcp_docs.tools_access import (
    docs_create_invitation,
    docs_grant_access,
    docs_list_accesses,
    docs_list_invitations,
    docs_revoke_access,
    docs_update_access,
)

from .conftest import BASE_URL, make_config

API = f"{BASE_URL}/api/v1.0"

SAMPLE_ACCESS = {
    "id": "access-001",
    "user": "user-001",
    "role": "editor",
    "team": None,
}

SAMPLE_ACCESSES = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [SAMPLE_ACCESS],
}

SAMPLE_INVITATION = {
    "id": "inv-001",
    "email": "invitee@example.gouv.fr",
    "role": "reader",
    "issuer": None,
}

SAMPLE_INVITATIONS = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [SAMPLE_INVITATION],
}


@pytest.fixture
def docs_client() -> DocsClient:
    return DocsClient(make_config())


@pytest.fixture
def ctx(docs_client: DocsClient) -> MagicMock:
    context = MagicMock()
    context.request_context.lifespan_context = AppContext(config=make_config(), client=docs_client)
    return context


DOC_ID = "doc-001"


# --- docs_list_accesses ---


class TestListAccessesTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/{DOC_ID}/accesses/").mock(return_value=Response(200, json=SAMPLE_ACCESSES))
        result = await docs_list_accesses(ctx=ctx, document_id=DOC_ID)
        data = json.loads(result)
        assert data["count"] == 1
        assert data["accesses"][0]["role"] == "editor"

    @respx.mock
    async def test_auth_error(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/{DOC_ID}/accesses/").mock(return_value=Response(401))
        result = await docs_list_accesses(ctx=ctx, document_id=DOC_ID)
        assert "Authentication failed" in result

    async def test_empty_document_id(self, ctx: MagicMock) -> None:
        result = await docs_list_accesses(ctx=ctx, document_id="")
        assert "Error" in result


# --- docs_grant_access ---


class TestGrantAccessTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/accesses/").mock(return_value=Response(201, json=SAMPLE_ACCESS))
        result = await docs_grant_access(ctx=ctx, document_id=DOC_ID, user_id="user-001", role="editor")
        data = json.loads(result)
        assert data["role"] == "editor"

    @respx.mock
    async def test_forbidden(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/accesses/").mock(return_value=Response(403))
        result = await docs_grant_access(ctx=ctx, document_id=DOC_ID, user_id="user-001", role="editor")
        assert "Access denied" in result

    async def test_invalid_role(self, ctx: MagicMock) -> None:
        result = await docs_grant_access(ctx=ctx, document_id=DOC_ID, user_id="user-001", role="superadmin")
        assert "Error" in result

    async def test_empty_user_id(self, ctx: MagicMock) -> None:
        result = await docs_grant_access(ctx=ctx, document_id=DOC_ID, user_id="", role="reader")
        assert "Error" in result


# --- docs_update_access ---


class TestUpdateAccessTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        updated = {**SAMPLE_ACCESS, "role": "administrator"}
        respx.patch(f"{API}/documents/{DOC_ID}/accesses/access-001/").mock(
            return_value=Response(200, json=updated)
        )
        result = await docs_update_access(ctx=ctx, document_id=DOC_ID, access_id="access-001", role="administrator")
        data = json.loads(result)
        assert data["role"] == "administrator"

    async def test_invalid_role(self, ctx: MagicMock) -> None:
        result = await docs_update_access(ctx=ctx, document_id=DOC_ID, access_id="a1", role="bad")
        assert "Error" in result

    async def test_empty_access_id(self, ctx: MagicMock) -> None:
        result = await docs_update_access(ctx=ctx, document_id=DOC_ID, access_id="", role="reader")
        assert "Error" in result


# --- docs_revoke_access ---


class TestRevokeAccessTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.delete(f"{API}/documents/{DOC_ID}/accesses/access-001/").mock(return_value=Response(204))
        result = await docs_revoke_access(ctx=ctx, document_id=DOC_ID, access_id="access-001")
        data = json.loads(result)
        assert data["status"] == "revoked"

    @respx.mock
    async def test_not_found(self, ctx: MagicMock) -> None:
        respx.delete(f"{API}/documents/{DOC_ID}/accesses/bad/").mock(return_value=Response(404))
        result = await docs_revoke_access(ctx=ctx, document_id=DOC_ID, access_id="bad")
        assert "not found" in result.lower()

    async def test_empty_access_id(self, ctx: MagicMock) -> None:
        result = await docs_revoke_access(ctx=ctx, document_id=DOC_ID, access_id="")
        assert "Error" in result


# --- docs_list_invitations ---


class TestListInvitationsTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.get(f"{API}/documents/{DOC_ID}/invitations/").mock(
            return_value=Response(200, json=SAMPLE_INVITATIONS)
        )
        result = await docs_list_invitations(ctx=ctx, document_id=DOC_ID)
        data = json.loads(result)
        assert data["count"] == 1
        assert data["invitations"][0]["email"] == "invitee@example.gouv.fr"

    async def test_empty_document_id(self, ctx: MagicMock) -> None:
        result = await docs_list_invitations(ctx=ctx, document_id="")
        assert "Error" in result


# --- docs_create_invitation ---


class TestCreateInvitationTool:
    @respx.mock
    async def test_success(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/invitations/").mock(
            return_value=Response(201, json=SAMPLE_INVITATION)
        )
        result = await docs_create_invitation(
            ctx=ctx, document_id=DOC_ID, email="invitee@example.gouv.fr", role="reader"
        )
        data = json.loads(result)
        assert data["email"] == "invitee@example.gouv.fr"
        assert data["role"] == "reader"

    async def test_invalid_role_owner(self, ctx: MagicMock) -> None:
        result = await docs_create_invitation(ctx=ctx, document_id=DOC_ID, email="a@b.fr", role="owner")
        assert "Error" in result

    async def test_empty_email(self, ctx: MagicMock) -> None:
        result = await docs_create_invitation(ctx=ctx, document_id=DOC_ID, email="", role="reader")
        assert "Error" in result

    @respx.mock
    async def test_forbidden(self, ctx: MagicMock) -> None:
        respx.post(f"{API}/documents/{DOC_ID}/invitations/").mock(return_value=Response(403))
        result = await docs_create_invitation(ctx=ctx, document_id=DOC_ID, email="a@b.fr", role="reader")
        assert "Access denied" in result
