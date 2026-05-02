"""Data schemas used by the Triage Agent."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


IssueType = Literal["bug", "feature", "refactor", "unknown"]
PriorityLevel = Literal["low", "medium", "high"]


class TriageSummary(BaseModel):
    """Structured triage output prepared for downstream agents."""

    issue_id: str = Field(..., description="Identifier of the issue being triaged.")
    issue_type: IssueType = Field(..., description="High-level issue classification.")
    priority: PriorityLevel = Field(..., description="Estimated issue priority.")
    normalized_title: str = Field(..., description="Normalized short issue title.")
    normalized_description: str = Field(
        ...,
        description="Cleaned issue description for downstream use.",
    )
    expected_behavior: Optional[str] = Field(
        default=None,
        description="Expected behavior if it can be extracted confidently.",
    )
    search_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords recommended for repository analysis.",
    )
    summary: str = Field(
        ...,
        description="Short triage explanation for the engineering team.",
    )


class TriageArtifact(BaseModel):
    """Serializable triage-agent payload written for downstream use."""

    summary: TriageSummary
    artifact_path: str = Field(
        ...,
        description="Filesystem path where the triage artifact is stored.",
    )
