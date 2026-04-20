"""Patch Generation Agent starter module.

This agent will consume structured issue context and repository findings,
then prepare a minimal patch proposal for downstream validation.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from agents.patch_agent.prompt import (
    PATCH_AGENT_SYSTEM_PROMPT,
    build_patch_agent_user_prompt,
)
from agents.patch_agent.schema import PatchChangePlan, PatchProposal
from agents.patch_agent.utils import (
    build_validation_focus,
    estimate_risk_level,
    collect_candidate_files,
    summarize_change_scope,
)
from orchestrator.state import PatchWorkflowState
from tools.patch_tools.patch_writer import write_patch_artifact

logger = logging.getLogger(__name__)


class PatchProposalGenerator(Protocol):
    """Protocol for model-backed patch proposal generation."""

    def generate(self, state: PatchWorkflowState) -> PatchProposal:
        """Build a structured patch proposal from shared workflow state."""


class OllamaPatchProposalGenerator:
    """Generate structured patch proposals with Ollama via LangChain."""

    def __init__(self, model_name: str, base_url: str) -> None:
        """Store connection details for deferred Ollama initialization."""

        self.model_name = model_name
        self.base_url = base_url

    def generate(self, state: PatchWorkflowState) -> PatchProposal:
        """Call the local Ollama model and coerce output into PatchProposal."""

        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError(
                "langchain-ollama is not installed. Install requirements first."
            ) from exc

        llm = ChatOllama(
            model=self.model_name,
            base_url=self.base_url,
            temperature=0,
        ).with_structured_output(PatchProposal)

        return llm.invoke(
            [
                ("system", PATCH_AGENT_SYSTEM_PROMPT),
                ("human", build_patch_agent_user_prompt(state)),
            ]
        )


class PatchGenerationAgent:
    """Specialized agent responsible for proposing minimal code patches."""

    def __init__(
        self,
        output_dir: str = "outputs/patches",
        proposal_generator: Optional[PatchProposalGenerator] = None,
        allow_fallback: bool = True,
    ) -> None:
        """Initialize the agent with configurable generation behavior."""

        self.output_dir = output_dir
        self.proposal_generator = proposal_generator
        self.allow_fallback = allow_fallback

    def run(self, state: PatchWorkflowState) -> PatchWorkflowState:
        """Build a minimal structured patch proposal from shared state.

        Args:
            state: Shared workflow state containing issue context and
                repository findings from earlier agents.

        Returns:
            Updated workflow state with a serialized patch proposal artifact.
        """

        logger.info(
            "PatchGenerationAgent started for issue_id=%s with %d repository findings",
            state.issue.issue_id,
            len(state.repository_findings),
        )
        proposal = self._generate_proposal(state)
        state.patch_agent_output = write_patch_artifact(
            proposal=proposal,
            output_dir=self.output_dir,
        )
        logger.info(
            "PatchGenerationAgent completed for issue_id=%s target_files=%s artifact_path=%s risk_level=%s",
            proposal.issue_id,
            ",".join(proposal.target_files),
            state.patch_agent_output.artifact_path,
            proposal.risk_level,
        )
        return state

    def _generate_proposal(self, state: PatchWorkflowState) -> PatchProposal:
        """Use the configured generator and fall back when appropriate."""

        if self.proposal_generator is None:
            logger.info(
                "PatchGenerationAgent using deterministic proposal generation for issue_id=%s",
                state.issue.issue_id,
            )
            return self._build_fallback_proposal(state)

        try:
            logger.info(
                "PatchGenerationAgent requesting model-backed proposal for issue_id=%s",
                state.issue.issue_id,
            )
            proposal = self.proposal_generator.generate(state)
            self._validate_proposal_quality(proposal)
            logger.info(
                "PatchGenerationAgent accepted model-backed proposal for issue_id=%s",
                state.issue.issue_id,
            )
            return proposal
        except Exception as exc:
            if not self.allow_fallback:
                logger.exception(
                    "PatchGenerationAgent failed without fallback for issue_id=%s",
                    state.issue.issue_id,
                )
                raise
            logger.warning(
                "PatchGenerationAgent falling back for issue_id=%s reason=%s",
                state.issue.issue_id,
                exc,
            )
            return self._build_fallback_proposal(state)

    def _build_fallback_proposal(self, state: PatchWorkflowState) -> PatchProposal:
        """Create a deterministic patch proposal when no model is available."""

        target_files = collect_candidate_files(state.repository_findings)
        risk_level = estimate_risk_level(target_files)
        logger.info(
            "PatchGenerationAgent fallback selected target_files=%s risk_level=%s for issue_id=%s",
            ",".join(target_files),
            risk_level,
            state.issue.issue_id,
        )

        change_plan = [
            PatchChangePlan(
                file_path=finding.file_path,
                change_summary=summarize_change_scope(finding),
                evidence=finding.reason,
            )
            for finding in state.repository_findings[:3]
        ]

        rationale_parts = [
            f"Issue focus: {state.issue.title}.",
            "The proposal is limited to files identified by the analysis output.",
        ]
        if state.repository_findings:
            rationale_parts.append(
                f"Primary evidence: {state.repository_findings[0].reason.rstrip('.')}."
            )

        return PatchProposal(
            issue_id=state.issue.issue_id,
            summary=f"Target a minimal fix for '{state.issue.title}'.",
            target_files=target_files,
            change_plan=change_plan,
            rationale=" ".join(rationale_parts),
            risk_level=risk_level,
            risk_notes=[
                "Edits should remain scoped to the identified files only.",
                f"Estimated impact is based on {len(target_files)} target file(s).",
            ],
            validation_focus=build_validation_focus(state.repository_findings),
        )

    def _validate_proposal_quality(self, proposal: PatchProposal) -> None:
        """Reject incomplete model output before it reaches validation.

        Args:
            proposal: Structured proposal returned by the model-backed generator.

        Raises:
            ValueError: If essential patch fields are empty or inconsistent.
        """

        if not proposal.target_files:
            raise ValueError("Model output must include at least one target file.")

        if not proposal.change_plan:
            raise ValueError("Model output must include at least one change-plan item.")

        planned_files = {item.file_path for item in proposal.change_plan}
        missing_targets = [path for path in proposal.target_files if path not in planned_files]
        if missing_targets:
            raise ValueError(
                "Model output has target files without matching change-plan entries: "
                + ", ".join(missing_targets)
            )
