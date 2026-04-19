"""Shared state definitions passed between agents.

The final workflow will enrich this structure as each specialized agent
adds its own outputs. This version keeps the state strongly structured
around the Patch Generation Agent contract.
"""

from pydantic import BaseModel, Field

from agents.patch_agent.schema import PatchArtifact


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
    line_start: int | None = Field(
        default=None,
        description="Optional starting line number for the snippet.",
    )
    line_end: int | None = Field(
        default=None,
        description="Optional ending line number for the snippet.",
    )


class PatchWorkflowState(BaseModel):
    """Shared state container used by the orchestrator and agents."""

    issue: IssueContext
    repository_findings: list[RepositoryFinding] = Field(default_factory=list)
    patch_agent_output: PatchArtifact | None = Field(
        default=None,
        description="Structured patch proposal prepared for validation.",
    )
