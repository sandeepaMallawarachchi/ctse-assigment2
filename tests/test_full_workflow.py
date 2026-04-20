"""Starter integration-style tests for shared workflow state."""

from orchestrator.state import IssueContext, PatchWorkflowState


def test_patch_workflow_state_starts_without_patch_output() -> None:
    """Shared workflow state should allow the patch stage to populate later."""

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-003",
            title="Example issue",
            description="Example description",
        )
    )

    assert state.patch_agent_output is None


def test_patch_workflow_state_starts_without_analysis_output() -> None:
    """Shared workflow state should allow the analysis stage to populate later."""

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-006",
            title="Example issue",
            description="Example description",
        )
    )

    assert state.analysis_output is None
