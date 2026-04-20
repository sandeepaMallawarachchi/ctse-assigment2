"""Data schemas used by the Codebase Analysis Agent."""

from typing import Optional

from pydantic import BaseModel, Field


class AnalysisQuery(BaseModel):
    """Structured description of what the analysis agent should inspect."""

    issue_id: str = Field(..., description="Identifier of the issue being analyzed.")
    search_terms: list[str] = Field(
        default_factory=list,
        description="Issue-derived keywords for repository search.",
    )
    repo_path: str = Field(..., description="Local repository path to inspect.")


class AnalysisFinding(BaseModel):
    """Relevant code location surfaced by the analysis stage."""

    file_path: str = Field(..., description="Candidate file related to the issue.")
    snippet: str = Field(..., description="Relevant code snippet from the repository.")
    reason: str = Field(..., description="Why this file/snippet is relevant.")
    line_start: Optional[int] = Field(
        default=None,
        description="Optional starting line number for the snippet.",
    )
    line_end: Optional[int] = Field(
        default=None,
        description="Optional ending line number for the snippet.",
    )


class AnalysisSummary(BaseModel):
    """Structured output produced by the analysis stage."""

    issue_id: str = Field(..., description="Identifier of the issue being analyzed.")
    repo_path: str = Field(..., description="Local repository path that was inspected.")
    search_terms: list[str] = Field(
        default_factory=list,
        description="Keywords used during repository inspection.",
    )
    findings: list[AnalysisFinding] = Field(
        default_factory=list,
        description="Relevant repository findings for downstream patch generation.",
    )
    summary: str = Field(
        ...,
        description="Short natural-language overview of the relevant files discovered.",
    )


class AnalysisArtifact(BaseModel):
    """Serializable analysis-agent payload written for downstream use."""

    summary: AnalysisSummary
    artifact_path: str = Field(
        ...,
        description="Filesystem path where the analysis artifact is stored.",
    )
