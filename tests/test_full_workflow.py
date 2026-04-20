"""Starter integration-style tests for shared workflow state."""

import json
from pathlib import Path

from app.main import apply_analysis_artifact_to_state
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


def test_apply_analysis_artifact_to_state_populates_findings(tmp_path: Path) -> None:
    """Patch runs should be able to consume a prior analysis artifact."""

    artifact_path = tmp_path / "analysis.json"
    artifact_payload = {
        "summary": {
            "issue_id": "ISSUE-300",
            "repo_path": "data/repo_mock",
            "search_terms": ["login", "spinner"],
            "findings": [
                {
                    "file_path": "src/auth/login_handler.py",
                    "snippet": "if login_failed:",
                    "reason": "Failure branch appears relevant.",
                    "line_start": 10,
                    "line_end": 12,
                }
            ],
            "summary": "Found one relevant auth file.",
        },
        "artifact_path": str(artifact_path),
    }
    artifact_path.write_text(json.dumps(artifact_payload), encoding="utf-8")

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-300",
            title="Fix login spinner",
            description="Spinner stays active after failure.",
        )
    )
    updated_state = apply_analysis_artifact_to_state(state, str(artifact_path))

    assert updated_state.analysis_output is not None
    assert updated_state.repository_root == "data/repo_mock"
    assert len(updated_state.repository_findings) == 1
    assert updated_state.repository_findings[0].file_path == "src/auth/login_handler.py"
