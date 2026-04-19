"""Patch Generation Agent starter module.

This agent will consume structured issue context and repository findings,
then prepare a minimal patch proposal for downstream validation.
"""

from orchestrator.state import PatchWorkflowState


class PatchGenerationAgent:
    """Specialized agent responsible for proposing minimal code patches."""

    def run(self, state: PatchWorkflowState) -> PatchWorkflowState:
        """Return state unchanged until patch generation logic is added."""
        return state
