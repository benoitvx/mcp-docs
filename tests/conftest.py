"""Shared test fixtures."""

import pytest

from mcp_docs.client import DocsClient

BASE_URL = "https://docs.test.local"


@pytest.fixture
def docs_client_session() -> DocsClient:
    """DocsClient configured with session cookie auth."""
    return DocsClient(
        base_url=BASE_URL,
        auth_mode="session",
        session_cookie="test-session-id",
    )


@pytest.fixture
def docs_client_oidc() -> DocsClient:
    """DocsClient configured with OIDC bearer token auth."""
    return DocsClient(
        base_url=BASE_URL,
        auth_mode="oidc",
        oidc_token="test-oidc-token",
    )


SAMPLE_DOCUMENTS = {
    "count": 2,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": "aaaa-bbbb-cccc-0001",
            "title": "Document One",
            "created_at": "2026-01-01T10:00:00Z",
            "updated_at": "2026-04-01T12:00:00Z",
        },
        {
            "id": "aaaa-bbbb-cccc-0002",
            "title": "Document Two",
            "created_at": "2026-02-01T10:00:00Z",
            "updated_at": "2026-03-15T08:00:00Z",
        },
    ],
}

SAMPLE_CONTENT = {
    "id": "aaaa-bbbb-cccc-0001",
    "title": "Document One",
    "content": "Hello **world**",
    "created_at": "2026-01-01T10:00:00Z",
    "updated_at": "2026-04-01T12:00:00Z",
}

SAMPLE_CREATED = {
    "id": "aaaa-bbbb-cccc-9999",
    "title": "New Document",
}

SAMPLE_USER = {
    "id": "user-001",
    "email": "user@example.gouv.fr",
    "name": "Test User",
}
