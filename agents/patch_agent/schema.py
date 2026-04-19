"""Data schemas used by the Patch Generation Agent."""

from pydantic import BaseModel, Field


class PatchProposal(BaseModel):
    """Structured output prepared by the patch agent for validation."""

    summary: str = Field(..., description="Short explanation of the proposed fix.")
    target_files: list[str] = Field(
        default_factory=list,
        description="Files expected to be edited by the proposed patch.",
    )
    rationale: str = Field(..., description="Why the patch should address the issue.")
    risk_level: str = Field(
        default="unknown",
        description="Initial qualitative risk estimate for the change.",
    )
