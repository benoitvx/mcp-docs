"""Pydantic models for Docs API responses."""

from datetime import datetime

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    """Lightweight document representation returned by list endpoints."""

    id: str
    title: str | None = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    creator: str | dict | None = None


class DocumentContent(BaseModel):
    """Full document content returned by the content endpoint."""

    id: str
    title: str | None = ""
    content: str | None = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginatedResponse[T](BaseModel):
    """Paginated API response wrapper."""

    count: int
    next: str | None = None
    previous: str | None = None
    results: list[T]


class UserInfo(BaseModel):
    """Authenticated user profile."""

    id: str
    email: str = ""
    name: str = ""


# --- Access / Invitation models (used by permission tools) ---


class DocumentAccess(BaseModel):
    """A user's access entry on a document."""

    id: str
    user: str | dict = ""
    role: str = ""
    team: str | None = None


class Invitation(BaseModel):
    """A pending invitation to a document."""

    id: str
    email: str = ""
    role: str = ""
    issuer: str | dict | None = None
