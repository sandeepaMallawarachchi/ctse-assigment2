"""Validation & Report Agent module.

This agent consumes the patch proposal produced by the Patch Generation Agent,
runs deterministic structural checks, requests an LLM verdict, and writes a
final validation report artifact to disk.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from agents.patch_agent.schema import PatchProposal
from agents.validation_agent.prompt import (
    VALIDATION_AGENT_SYSTEM_PROMPT,
    build_validation_user_prompt,
)
from agents.validation_agent.schema import (
    FinalReport,
    ValidationCheck,
    ValidationVerdict,
)
from agents.validation_agent.utils import compute_verdict, run_structural_checks
from orchestrator.state import PatchWorkflowState
from tools.validation_tools.report_writer import write_validation_report

logger = logging.getLogger(__name__)


class ValidationVerdictGenerator(Protocol):
    """Protocol for model-backed validation verdict generation."""

    def generate(
        self,
        state: PatchWorkflowState,
        checks: list[ValidationCheck],
    ) -> tuple[ValidationVerdict, str]:
        """Produce a structured verdict and a short LLM assessment narrative.

        Args:
            state: Shared workflow state including the patch proposal.
            checks: Completed structural check results.

        Returns:
            Tuple of (ValidationVerdict, llm_assessment string).
        """


class OllamaValidationVerdictGenerator:
    """Generate a structured verdict by calling a local Ollama model."""

    def __init__(self, model_name: str, base_url: str) -> None:
        """Store Ollama connection details for deferred initialisation.

        Args:
            model_name: Ollama model identifier (e.g. "llama3.1").
            base_url: Base URL of the local Ollama server.
        """

        self.model_name = model_name
        self.base_url = base_url

    def generate(
        self,
        state: PatchWorkflowState,
        checks: list[ValidationCheck],
    ) -> tuple[ValidationVerdict, str]:
        """Call the local Ollama model and return a structured verdict.

        Args:
            state: Shared workflow state including the patch proposal.
            checks: Completed structural check results.

        Returns:
            Tuple of (ValidationVerdict, llm_assessment string).

        Raises:
            RuntimeError: If langchain-ollama is not installed.
        """

        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError(
                "langchain-ollama is not installed. Install requirements first."
            ) from exc

        from pydantic import BaseModel, Field

        class _LLMOutput(BaseModel):
            verdict: ValidationVerdict
            llm_assessment: str = Field(..., description="Short narrative under 80 words.")
            recommendation: str = Field(..., description="One actionable sentence.")

        llm = ChatOllama(
            model=self.model_name,
            base_url=self.base_url,
            temperature=0,
        ).with_structured_output(_LLMOutput)

        result: _LLMOutput = llm.invoke(
            [
                ("system", VALIDATION_AGENT_SYSTEM_PROMPT),
                ("human", build_validation_user_prompt(state, checks)),
            ]
        )

        verdict = ValidationVerdict(
            status=result.verdict.status,
            confidence=result.verdict.confidence,
            rationale=result.verdict.rationale,
            checks_passed=sum(1 for c in checks if c.status == "pass"),
            checks_failed=sum(1 for c in checks if c.status == "fail"),
            checks_warned=sum(1 for c in checks if c.status == "warning"),
        )
        return verdict, result.llm_assessment

    def _build_recommendation(self, status: str, risk_level: str) -> str:
        """Derive a one-sentence recommendation from verdict status and risk.

        Args:
            status: Verdict status string.
            risk_level: Risk level declared in the patch proposal.

        Returns:
            One-sentence recommendation string.
        """

        if status == "approved":
            return f"Proceed with the patch; risk is '{risk_level}' and all checks passed."
        if status == "rejected":
            return "Do not merge; revise the patch to address the failed checks."
        return "Hold for manual review before proceeding with this patch."


class ValidationAgent:
    """Specialized agent that validates a patch proposal and produces a final report."""

    def __init__(
        self,
        output_dir: str = "outputs/reports",
        verdict_generator: Optional[ValidationVerdictGenerator] = None,
        allow_fallback: bool = True,
    ) -> None:
        """Initialise the agent with configurable generation behaviour.

        Args:
            output_dir: Directory where validation report artifacts are written.
            verdict_generator: Optional model-backed generator. When None the
                agent uses the deterministic fallback via compute_verdict().
            allow_fallback: If True, silently fall back to the deterministic
                verdict when the model generator raises an exception.
        """

        self.output_dir = output_dir
        self.verdict_generator = verdict_generator
        self.allow_fallback = allow_fallback

    def run(self, state: PatchWorkflowState) -> PatchWorkflowState:
        """Validate the patch proposal and write a final report artifact.

        Runs deterministic structural checks, requests an LLM verdict (or falls
        back to a deterministic one), assembles a FinalReport, writes it to
        disk, and attaches the ValidationArtifact to the shared state.

        Args:
            state: Shared workflow state. Must contain a populated
                patch_agent_output field from the Patch Generation Agent.

        Returns:
            Updated workflow state with validation_output populated.

        Raises:
            ValueError: If patch_agent_output is missing from the state.
        """

        if state.patch_agent_output is None:
            raise ValueError(
                "ValidationAgent requires patch_agent_output to be set on state. "
                "Ensure the Patch Generation Agent has run first."
            )

        proposal: PatchProposal = state.patch_agent_output.proposal

        logger.info(
            "ValidationAgent started for issue_id=%s title=%r risk_level=%s target_files=%s",
            proposal.issue_id,
            proposal.issue_id,
            proposal.risk_level,
            ",".join(proposal.target_files) or "(none)",
        )

        checks = run_structural_checks(proposal)

        passed = sum(1 for c in checks if c.status == "pass")
        failed = sum(1 for c in checks if c.status == "fail")
        warned = sum(1 for c in checks if c.status == "warning")

        for check in checks:
            logger.debug(
                "ValidationAgent structural_check name=%s status=%s detail=%r",
                check.name,
                check.status,
                check.detail,
            )

        logger.info(
            "ValidationAgent structural checks complete for issue_id=%s "
            "passed=%d failed=%d warned=%d",
            proposal.issue_id,
            passed,
            failed,
            warned,
        )

        if failed > 0:
            failed_names = [c.name for c in checks if c.status == "fail"]
            logger.warning(
                "ValidationAgent issue_id=%s has %d failed check(s): %s",
                proposal.issue_id,
                failed,
                ", ".join(failed_names),
            )

        if warned > 0:
            warned_names = [c.name for c in checks if c.status == "warning"]
            logger.warning(
                "ValidationAgent issue_id=%s has %d warning(s): %s",
                proposal.issue_id,
                warned,
                ", ".join(warned_names),
            )

        verdict, llm_assessment = self._generate_verdict(state, checks, proposal)

        logger.info(
            "ValidationAgent verdict for issue_id=%s status=%s confidence=%s rationale=%r",
            proposal.issue_id,
            verdict.status,
            verdict.confidence,
            verdict.rationale,
        )

        recommendation = self._build_recommendation(verdict.status, proposal.risk_level)

        logger.debug(
            "ValidationAgent recommendation for issue_id=%s: %r",
            proposal.issue_id,
            recommendation,
        )

        report = FinalReport(
            issue_id=proposal.issue_id,
            patch_summary=proposal.summary,
            target_files=proposal.target_files,
            risk_level=proposal.risk_level,
            checks=checks,
            verdict=verdict,
            llm_assessment=llm_assessment,
            recommendation=recommendation,
        )

        state.validation_output = write_validation_report(
            report=report,
            output_dir=self.output_dir,
        )

        logger.info(
            "ValidationAgent completed for issue_id=%s verdict=%s confidence=%s "
            "artifact_path=%s",
            proposal.issue_id,
            verdict.status,
            verdict.confidence,
            state.validation_output.artifact_path,
        )

        return state

    def _generate_verdict(
        self,
        state: PatchWorkflowState,
        checks: list[ValidationCheck],
        proposal: PatchProposal,
    ) -> tuple[ValidationVerdict, str]:
        """Use the configured generator and fall back when appropriate.

        Args:
            state: Shared workflow state.
            checks: Completed structural check results.
            proposal: Patch proposal being validated.

        Returns:
            Tuple of (ValidationVerdict, llm_assessment string).
        """

        if self.verdict_generator is None:
            logger.info(
                "ValidationAgent using deterministic verdict for issue_id=%s",
                proposal.issue_id,
            )
            return self._build_fallback_verdict(checks, proposal)

        try:
            logger.info(
                "ValidationAgent requesting model-backed verdict for issue_id=%s",
                proposal.issue_id,
            )
            verdict, assessment = self.verdict_generator.generate(state, checks)
            logger.info(
                "ValidationAgent accepted model-backed verdict for issue_id=%s",
                proposal.issue_id,
            )
            return verdict, assessment
        except Exception as exc:
            if not self.allow_fallback:
                logger.exception(
                    "ValidationAgent failed without fallback for issue_id=%s",
                    proposal.issue_id,
                )
                raise
            logger.warning(
                "ValidationAgent falling back for issue_id=%s reason=%s",
                proposal.issue_id,
                exc,
            )
            return self._build_fallback_verdict(checks, proposal)

    def _build_fallback_verdict(
        self,
        checks: list[ValidationCheck],
        proposal: PatchProposal,
    ) -> tuple[ValidationVerdict, str]:
        """Build a deterministic verdict when no model is available.

        Args:
            checks: Completed structural check results.
            proposal: Patch proposal being validated.

        Returns:
            Tuple of (ValidationVerdict, llm_assessment string).
        """

        verdict = compute_verdict(checks, proposal.risk_level)
        failed_names = [c.name for c in checks if c.status == "fail"]
        warned_names = [c.name for c in checks if c.status == "warning"]

        logger.info(
            "ValidationAgent deterministic verdict for issue_id=%s "
            "status=%s confidence=%s failed=%s warned=%s",
            proposal.issue_id,
            verdict.status,
            verdict.confidence,
            ",".join(failed_names) or "none",
            ",".join(warned_names) or "none",
        )

        parts: list[str] = [
            f"Deterministic review of proposal for '{proposal.issue_id}'."
        ]
        if failed_names:
            parts.append(f"Failed checks: {', '.join(failed_names)}.")
        if warned_names:
            parts.append(f"Warnings raised: {', '.join(warned_names)}.")
        if not failed_names and not warned_names:
            parts.append("All structural checks passed cleanly.")

        return verdict, " ".join(parts)

    @staticmethod
    def _build_recommendation(status: str, risk_level: str) -> str:
        """Derive a one-sentence recommendation from verdict status and risk level.

        Args:
            status: Verdict status string (approved/rejected/needs_review).
            risk_level: Risk level declared in the patch proposal.

        Returns:
            One-sentence recommendation string for the engineering team.
        """

        if status == "approved":
            return (
                f"Proceed with the patch; risk is '{risk_level}' "
                "and all structural checks passed."
            )
        if status == "rejected":
            return (
                "Do not merge; revise the patch to address the failed "
                "structural checks before resubmitting."
            )
        return (
            "Hold for manual review — one or more checks raised warnings "
            "that should be resolved before merging."
        )
