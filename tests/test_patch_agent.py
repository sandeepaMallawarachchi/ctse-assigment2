from __future__ import annotations

"""Tests for the Patch Generation Agent starter flow."""

import json
from pathlib import Path
from typing import Optional

from agents.patch_agent.agent import PatchGenerationAgent
from agents.patch_agent.prompt import build_patch_agent_user_prompt
from agents.patch_agent.schema import PatchChangePlan, PatchProposal
from agents.patch_agent.utils import collect_candidate_files
from orchestrator.state import IssueContext, PatchWorkflowState, RepositoryFinding


class FakeProposalGenerator:
    """Small fake model generator for prompt/output contract testing."""

    def __init__(self) -> None:
        self.last_prompt: Optional[str] = None

    def generate(self, state: PatchWorkflowState) -> PatchProposal:
        """Return a fixed structured proposal and capture the rendered prompt."""

        self.last_prompt = build_patch_agent_user_prompt(state)
        return PatchProposal(
            issue_id=state.issue.issue_id,
            summary="Reset the loading state after a failed login attempt.",
            target_files=["app/auth.py"],
            change_plan=[
                PatchChangePlan(
                    file_path="app/auth.py",
                    change_summary="Clear spinner state in the failure branch.",
                    evidence="The failure path leaves the UI in a loading state.",
                )
            ],
            rationale="A focused change in the failure path should resolve the stuck spinner.",
            risk_level="low",
            risk_notes=["Only one file is affected in the proposal."],
            validation_focus=["Confirm spinner stops after failed authentication."],
        )


class EmptyProposalGenerator:
    """Fake generator that simulates weak model output."""

    def generate(self, state: PatchWorkflowState) -> PatchProposal:
        """Return an incomplete proposal that should trigger fallback."""

        return PatchProposal(
            issue_id=state.issue.issue_id,
            summary="Attempted patch proposal.",
            target_files=[],
            change_plan=[],
            rationale="The model identified the general area but omitted file-level actions.",
            risk_level="low",
            risk_notes=[],
            validation_focus=["Inspect login flow manually."],
        )


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


def test_patch_generation_agent_accepts_model_backed_structured_output(
    tmp_path: Path,
) -> None:
    """The agent should accept structured output from a model adapter."""

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-004",
            title="Fix login spinner state",
            description="Spinner does not stop after failed login.",
            expected_behavior="Spinner should stop and error feedback should appear.",
        ),
        repository_findings=[
            RepositoryFinding(
                file_path="app/auth.py",
                snippet="spinner = True",
                reason="The failure path seems not to reset spinner state.",
            )
        ],
    )
    fake_generator = FakeProposalGenerator()
    agent = PatchGenerationAgent(
        output_dir=str(tmp_path),
        proposal_generator=fake_generator,
    )

    updated_state = agent.run(state)

    assert updated_state.patch_agent_output is not None
    assert updated_state.patch_agent_output.proposal.summary.startswith("Reset the")
    assert "Issue Title: Fix login spinner state" in (fake_generator.last_prompt or "")
    assert "file=app/auth.py" in (fake_generator.last_prompt or "")


def test_patch_generation_agent_falls_back_on_empty_model_output(
    tmp_path: Path,
) -> None:
    """Incomplete model output should be replaced with a usable fallback proposal."""

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-005",
            title="Fix loading spinner after error",
            description="The spinner stays active after an API error.",
        ),
        repository_findings=[
            RepositoryFinding(
                file_path="app/auth.py",
                snippet="spinner = True",
                reason="The failure path does not appear to clear loading state.",
            ),
            RepositoryFinding(
                file_path="app/ui.py",
                snippet="submit_button.loading = state.loading",
                reason="The UI reflects the stale loading state.",
            ),
        ],
    )

    agent = PatchGenerationAgent(
        output_dir=str(tmp_path),
        proposal_generator=EmptyProposalGenerator(),
    )
    updated_state = agent.run(state)

    assert updated_state.patch_agent_output is not None
    assert updated_state.patch_agent_output.proposal.target_files == [
        "app/auth.py",
        "app/ui.py",
    ]
    assert len(updated_state.patch_agent_output.proposal.change_plan) == 2
