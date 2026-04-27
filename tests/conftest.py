"""Shared test fixtures."""

import pytest

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig

BASE_URL = "https://docs.test.local"


def make_config(**overrides: object) -> DocsConfig:
    """Create a DocsConfig with test defaults, overridable per-field."""
    defaults: dict[str, object] = {
        "base_url": BASE_URL,
        "auth_mode": "session",
        "session_cookie": "test-session-id",
    }
    defaults.update(overrides)
    return DocsConfig(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def docs_client_session() -> DocsClient:
    """DocsClient configured with session cookie auth."""
    return DocsClient(make_config())


@pytest.fixture
def docs_client_oidc() -> DocsClient:
    """DocsClient configured with OIDC bearer token auth."""
    return DocsClient(make_config(auth_mode="oidc", session_cookie=None, oidc_token="test-oidc-token"))


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

SAMPLE_DOCUMENT_DETAIL = {
    "id": "aaaa-bbbb-cccc-0001",
    "title": "Document One",
    "creator": "user-001",
    "created_at": "2026-01-01T10:00:00Z",
    "updated_at": "2026-04-01T12:00:00Z",
}

SAMPLE_DOCUMENT_DETAIL_OTHER_CREATOR = {
    "id": "aaaa-bbbb-cccc-0002",
    "title": "Shared Document",
    "creator": "user-999",
    "created_at": "2026-01-01T10:00:00Z",
    "updated_at": "2026-04-01T12:00:00Z",
}

SAMPLE_CHILDREN = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": "aaaa-bbbb-cccc-child-01",
            "title": "Child Document",
            "created_at": "2026-03-01T10:00:00Z",
            "updated_at": "2026-04-05T14:00:00Z",
        },
    ],
}
