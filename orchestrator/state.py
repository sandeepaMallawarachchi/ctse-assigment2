"""Shared state definitions passed between agents.

The final workflow will enrich this structure as each specialized agent
adds its own outputs. This starter version focuses on fields needed by
the Patch Generation Agent.
"""

from typing import Any

from pydantic import BaseModel, Field


class IssueContext(BaseModel):
    """Structured issue information produced by earlier agents."""

    issue_id: str = Field(..., description="Unique identifier for the issue.")
    title: str = Field(..., description="Short issue title.")
    description: str = Field(..., description="Expanded issue or bug report.")
    expected_behavior: str | None = Field(
        default=None,
        description="Optional expected behavior extracted during triage.",
    )


class RepositoryFinding(BaseModel):
    """Relevant codebase evidence supplied by the analysis agent."""

    file_path: str = Field(..., description="Candidate file related to the issue.")
    snippet: str = Field(..., description="Relevant code snippet from the repository.")
    reason: str = Field(..., description="Why this file/snippet is relevant.")


class PatchWorkflowState(BaseModel):
    """Shared state container used by the orchestrator and agents."""

    issue: IssueContext
    repository_findings: list[RepositoryFinding] = Field(default_factory=list)
    patch_agent_output: dict[str, Any] | None = Field(
        default=None,
        description="Serialized patch proposal prepared for validation.",
    )
