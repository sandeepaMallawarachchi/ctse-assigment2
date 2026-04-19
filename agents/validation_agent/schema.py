"""Data schemas used by the Validation & Report Agent."""

from typing import Literal

from pydantic import BaseModel, Field


ValidationStatus = Literal["pass", "fail", "warning"]
VerdictStatus = Literal["approved", "rejected", "needs_review"]
ConfidenceLevel = Literal["high", "medium", "low"]


class ValidationCheck(BaseModel):
    """Result of a single deterministic structural check on a patch proposal."""

    name: str = Field(..., description="Short identifier for this check.")
    status: ValidationStatus = Field(
        ..., description="Outcome of the check: pass, fail, or warning."
    )
    detail: str = Field(
        ..., description="Human-readable explanation of the check result."
    )


class ValidationVerdict(BaseModel):
    """Structured verdict produced by the LLM or deterministic fallback."""

    status: VerdictStatus = Field(
        ...,
        description="Final decision: approved, rejected, or needs_review.",
    )
    confidence: ConfidenceLevel = Field(
        ...,
        description="Confidence level of the verdict based on available evidence.",
    )
    rationale: str = Field(
        ...,
        description="Short explanation justifying the verdict and confidence.",
    )
    checks_passed: int = Field(
        ..., description="Number of structural checks that passed."
    )
    checks_failed: int = Field(
        ..., description="Number of structural checks that failed."
    )
    checks_warned: int = Field(
        ..., description="Number of structural checks that produced a warning."
    )


class FinalReport(BaseModel):
    """Complete validation report combining structural checks and LLM assessment."""

    issue_id: str = Field(..., description="Identifier of the issue being validated.")
    patch_summary: str = Field(
        ..., description="Summary of the patch proposal under review."
    )
    target_files: list[str] = Field(
        default_factory=list,
        description="Files the patch proposal intends to modify.",
    )
    risk_level: str = Field(
        ..., description="Risk level declared by the Patch Generation Agent."
    )
    checks: list[ValidationCheck] = Field(
        default_factory=list,
        description="Ordered list of deterministic structural check results.",
    )
    verdict: ValidationVerdict = Field(
        ..., description="Final verdict produced by the LLM or deterministic fallback."
    )
    llm_assessment: str = Field(
        ...,
        description="Short narrative assessment from the validation model.",
    )
    recommendation: str = Field(
        ...,
        description="One-sentence final recommendation for the engineering team.",
    )


class ValidationArtifact(BaseModel):
    """Serializable validation-agent payload written for downstream consumption."""

    report: FinalReport
    artifact_path: str = Field(
        ...,
        description="Filesystem path where the serialized validation report is stored.",
    )
