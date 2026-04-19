"""Tests for the Patch Generation Agent starter flow."""

import json
from pathlib import Path

from agents.patch_agent.agent import PatchGenerationAgent
from agents.patch_agent.utils import collect_candidate_files
from orchestrator.state import IssueContext, PatchWorkflowState, RepositoryFinding


def test_collect_candidate_files_returns_unique_paths() -> None:
    """The helper should preserve order while removing duplicates."""

    findings = [
        RepositoryFinding(file_path="app/auth.py", snippet="a", reason="auth flow"),
        RepositoryFinding(file_path="app/auth.py", snippet="b", reason="retry logic"),
        RepositoryFinding(file_path="app/ui.py", snippet="c", reason="button state"),
    ]

    assert collect_candidate_files(findings) == ["app/auth.py", "app/ui.py"]


def test_patch_generation_agent_writes_structured_artifact(tmp_path: Path) -> None:
    """The agent should produce a typed artifact for downstream validation."""

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-002",
            title="Fix retry state handling",
            description="Retry button remains disabled after a failed request.",
            expected_behavior="Retry button should become active again.",
        ),
        repository_findings=[
            RepositoryFinding(
                file_path="app/retry.py",
                snippet="retry_enabled = False",
                reason="This file controls retry state.",
                line_start=10,
                line_end=18,
            ),
            RepositoryFinding(
                file_path="app/ui.py",
                snippet="button.disabled = loading",
                reason="This view updates the disabled button state.",
            ),
        ],
    )

    agent = PatchGenerationAgent(output_dir=str(tmp_path))
    updated_state = agent.run(state)

    assert updated_state.patch_agent_output is not None
    assert updated_state.patch_agent_output.proposal.issue_id == "ISSUE-002"
    assert updated_state.patch_agent_output.proposal.target_files == [
        "app/retry.py",
        "app/ui.py",
    ]
    artifact_path = Path(updated_state.patch_agent_output.artifact_path)
    assert artifact_path.exists()

    artifact_content = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_content["issue_id"] == "ISSUE-002"
    assert artifact_content["risk_level"] == "medium"
