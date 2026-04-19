"""Patch Generation Agent starter module.

This agent will consume structured issue context and repository findings,
then prepare a minimal patch proposal for downstream validation.
"""

from agents.patch_agent.schema import PatchChangePlan, PatchProposal
from agents.patch_agent.utils import (
    build_validation_focus,
    collect_candidate_files,
    estimate_risk_level,
    summarize_change_scope,
)
from orchestrator.state import PatchWorkflowState
from tools.patch_tools.patch_writer import write_patch_artifact


class PatchGenerationAgent:
    """Specialized agent responsible for proposing minimal code patches."""

    def __init__(self, output_dir: str = "outputs/patches") -> None:
        """Initialize the agent with a configurable artifact directory."""

        self.output_dir = output_dir

    def run(self, state: PatchWorkflowState) -> PatchWorkflowState:
        """Build a minimal structured patch proposal from shared state.

        Args:
            state: Shared workflow state containing issue context and
                repository findings from earlier agents.

        Returns:
            Updated workflow state with a serialized patch proposal artifact.
        """

        target_files = collect_candidate_files(state.repository_findings)
        risk_level = estimate_risk_level(target_files)

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
                f"Primary evidence: {state.repository_findings[0].reason}."
            )

        proposal = PatchProposal(
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
        state.patch_agent_output = write_patch_artifact(
            proposal=proposal,
            output_dir=self.output_dir,
        )
        return state
