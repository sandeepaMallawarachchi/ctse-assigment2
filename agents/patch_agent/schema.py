"""Data schemas used by the Patch Generation Agent."""

from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high"]


class PatchChangePlan(BaseModel):
    """Describe a single targeted file modification proposal."""

    file_path: str = Field(..., description="Repository file intended for editing.")
    change_summary: str = Field(
        ...,
        description="Short explanation of the proposed change in this file.",
    )
    evidence: str = Field(
        ...,
        description="Repository evidence used to justify touching this file.",
    )


class PatchProposal(BaseModel):
    """Structured patch proposal prepared for the Validation Agent."""

    issue_id: str = Field(..., description="Identifier of the issue being addressed.")
    summary: str = Field(..., description="Short explanation of the proposed fix.")
    target_files: list[str] = Field(
        default_factory=list,
        description="Files expected to be edited by the proposed patch.",
    )
    change_plan: list[PatchChangePlan] = Field(
        default_factory=list,
        description="Minimal file-level change plan for the proposed patch.",
    )
    rationale: str = Field(..., description="Why the patch should address the issue.")
    risk_level: RiskLevel = Field(
        ...,
        description="Qualitative risk estimate for the proposed patch.",
    )
    risk_notes: list[str] = Field(
        default_factory=list,
        description="Small set of reasons supporting the risk estimate.",
    )
    validation_focus: list[str] = Field(
        default_factory=list,
        description="Checks the Validation Agent should prioritize.",
    )


class PatchArtifact(BaseModel):
    """Serializable patch-agent payload written for downstream review."""

    proposal: PatchProposal
    artifact_path: str = Field(
        ...,
        description="Filesystem path where the serialized artifact is stored.",
    )
    patch_draft: str = Field(
        ...,
        description="Unified-diff-style draft prepared by the custom patch tool.",
    )
    patch_draft_path: str = Field(
        ...,
        description="Filesystem path where the draft patch text is stored.",
    )
