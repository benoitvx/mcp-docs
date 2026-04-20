"""Tests for Pydantic response models."""

from datetime import UTC, datetime

from mcp_docs.models import (
    DocumentAccess,
    DocumentContent,
    DocumentSummary,
    Invitation,
    PaginatedResponse,
    UserInfo,
)


class TestDocumentSummary:
    def test_full_parse(self) -> None:
        doc = DocumentSummary.model_validate({
            "id": "abc-123",
            "title": "Test",
            "created_at": "2026-01-01T10:00:00Z",
            "updated_at": "2026-04-01T12:00:00Z",
        })
        assert doc.id == "abc-123"
        assert doc.title == "Test"
        assert doc.created_at == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    def test_minimal_parse(self) -> None:
        doc = DocumentSummary.model_validate({"id": "abc"})
        assert doc.id == "abc"
        assert doc.title == ""
        assert doc.created_at is None

    def test_extra_fields_ignored(self) -> None:
        doc = DocumentSummary.model_validate({"id": "x", "extra_field": 42})
        assert doc.id == "x"


class TestDocumentContent:
    def test_full_parse(self) -> None:
        dc = DocumentContent.model_validate({
            "id": "abc",
            "title": "Title",
            "content": "# Hello",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        })
        assert dc.content == "# Hello"

    def test_defaults(self) -> None:
        dc = DocumentContent.model_validate({"id": "abc"})
        assert dc.content == ""
        assert dc.title == ""


class TestPaginatedResponse:
    def test_document_list(self) -> None:
        data = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {"id": "1", "title": "A"},
                {"id": "2", "title": "B"},
            ],
        }
        resp = PaginatedResponse[DocumentSummary].model_validate(data)
        assert resp.count == 2
        assert len(resp.results) == 2
        assert isinstance(resp.results[0], DocumentSummary)
        assert resp.results[0].title == "A"

    def test_empty_results(self) -> None:
        resp = PaginatedResponse[DocumentSummary].model_validate({"count": 0, "results": []})
        assert resp.results == []


class TestUserInfo:
    def test_parse(self) -> None:
        user = UserInfo.model_validate({"id": "u1", "email": "a@b.fr", "name": "Alice"})
        assert user.email == "a@b.fr"

    def test_defaults(self) -> None:
        user = UserInfo.model_validate({"id": "u1"})
        assert user.email == ""
        assert user.name == ""


class TestDocumentAccess:
    def test_parse(self) -> None:
        access = DocumentAccess.model_validate({"id": "a1", "user": "u1", "role": "editor"})
        assert access.role == "editor"

    def test_user_as_dict(self) -> None:
        access = DocumentAccess.model_validate({"id": "a1", "user": {"id": "u1", "email": "x"}, "role": "reader"})
        assert isinstance(access.user, dict)


class TestInvitation:
    def test_parse(self) -> None:
        inv = Invitation.model_validate({"id": "i1", "email": "a@b.fr", "role": "reader"})
        assert inv.email == "a@b.fr"
        assert inv.issuer is None
