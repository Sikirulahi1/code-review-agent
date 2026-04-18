from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Review(SQLModel, table=True):
    __tablename__ = "reviews"

    id: Optional[int] = Field(default=None, primary_key=True)
    repo_owner: str = Field(index=True, max_length=255)
    repo_name: str = Field(index=True, max_length=255)
    pr_number: int = Field(index=True)
    commit_sha: str = Field(index=True, max_length=64)
    recommendation: Optional[str] = Field(default=None, max_length=64)
    total_findings: int = Field(default=0)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=utc_now,
    )

    findings: list["Finding"] = Relationship(back_populates="review")


class Finding(SQLModel, table=True):
    __tablename__ = "findings"

    id: Optional[int] = Field(default=None, primary_key=True)
    review_id: int = Field(foreign_key="reviews.id", index=True)
    agent_name: str = Field(index=True, max_length=64)
    category: str = Field(index=True, max_length=64)
    severity: int = Field(ge=1, le=5)
    original_severity: Optional[int] = Field(default=None, ge=1, le=5)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    title: str = Field(max_length=500)
    description: str
    suggestion: Optional[str] = Field(default=None)
    code_fix: Optional[str] = Field(default=None)
    file_path: str = Field(index=True, max_length=1024)
    line_start: Optional[int] = Field(default=None, ge=1)
    line_end: Optional[int] = Field(default=None, ge=1)
    fingerprint: str = Field(index=True, max_length=64)
    diff_position: Optional[int] = Field(default=None, ge=1)
    comment_destination: str = Field(default="inline", max_length=32)
    mapping_failed: bool = Field(default=False)
    github_comment_id: Optional[int] = Field(default=None, index=True)
    status: str = Field(default="open", index=True, max_length=32)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=utc_now,
    )

    review: Review = Relationship(back_populates="findings")
