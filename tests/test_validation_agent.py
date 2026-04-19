from __future__ import annotations

"""Tests for the Validation & Report Agent."""

import json
from pathlib import Path
from typing import Optional

import pytest

from agents.patch_agent.schema import PatchArtifact, PatchChangePlan, PatchProposal
from agents.validation_agent.agent import ValidationAgent
from agents.validation_agent.schema import (
    ValidationArtifact,
    ValidationCheck,
    ValidationVerdict,
)
from agents.validation_agent.utils import (
    check_change_plan_coverage,
    check_risk_file_consistency,
    check_risk_notes_present,
    check_schema_completeness,
    check_validation_focus_populated,
    compute_verdict,
    run_structural_checks,
)
from orchestrator.state import IssueContext, PatchWorkflowState, RepositoryFinding
from tools.validation_tools.report_writer import (
    build_report_output_path,
    write_validation_report,
)
from agents.validation_agent.schema import FinalReport


# ---------------------------------------------------------------------------
# Shared fixtures and fakes
# ---------------------------------------------------------------------------


def _make_valid_proposal(
    issue_id: str = "ISSUE-010",
    risk_level: str = "low",
    target_files: Optional[list[str]] = None,
) -> PatchProposal:
    """Return a fully-populated, structurally valid PatchProposal."""

    files = target_files if target_files is not None else ["app/auth.py"]
    return PatchProposal(
        issue_id=issue_id,
        summary="Add a null check before accessing the user session object.",
        target_files=files,
        change_plan=[
            PatchChangePlan(
                file_path=f,
                change_summary=f"Guard against null session in {f}.",
                evidence="Session object is dereferenced without a null check.",
            )
            for f in files
        ],
        rationale="Null dereference on the session object causes the crash.",
        risk_level=risk_level,
        risk_notes=["Only one file is modified; blast radius is minimal."],
        validation_focus=["Confirm login no longer crashes when session is None."],
    )


def _make_valid_state(
    proposal: Optional[PatchProposal] = None,
    artifact_path: str = "outputs/patches/ISSUE-010_patch.json",
) -> PatchWorkflowState:
    """Return a workflow state with a populated patch_agent_output."""

    p = proposal or _make_valid_proposal()
    return PatchWorkflowState(
        issue=IssueContext(
            issue_id=p.issue_id,
            title="Login crashes on empty session",
            description="Application crashes when the session object is None at login.",
            expected_behavior="Login should fail gracefully with an error message.",
        ),
        repository_findings=[
            RepositoryFinding(
                file_path="app/auth.py",
                snippet="user = session.user",
                reason="Session object is accessed without a null guard.",
            )
        ],
        patch_agent_output=PatchArtifact(
            proposal=p,
            artifact_path=artifact_path,
        ),
    )


class FakeVerdictGenerator:
    """Injects a fixed verdict without calling Ollama — for testing only."""

    def __init__(self) -> None:
        self.last_state: Optional[PatchWorkflowState] = None
        self.last_checks: Optional[list[ValidationCheck]] = None

    def generate(
        self,
        state: PatchWorkflowState,
        checks: list[ValidationCheck],
    ) -> tuple[ValidationVerdict, str]:
        self.last_state = state
        self.last_checks = checks
        verdict = ValidationVerdict(
            status="approved",
            confidence="high",
            rationale="Fake generator: structural checks passed.",
            checks_passed=sum(1 for c in checks if c.status == "pass"),
            checks_failed=sum(1 for c in checks if c.status == "fail"),
            checks_warned=sum(1 for c in checks if c.status == "warning"),
        )
        return verdict, "Fake assessment: the proposal is narrow and well-justified."


class FailingVerdictGenerator:
    """Always raises — used to verify the fallback path activates correctly."""

    def generate(
        self,
        state: PatchWorkflowState,
        checks: list[ValidationCheck],
    ) -> tuple[ValidationVerdict, str]:
        raise RuntimeError("Simulated Ollama connection failure.")


# ---------------------------------------------------------------------------
# Structural check unit tests
# ---------------------------------------------------------------------------


def test_check_schema_completeness_passes_on_valid_proposal() -> None:
    """A proposal with non-empty summary and rationale should pass."""

    result = check_schema_completeness(_make_valid_proposal())
    assert result.status == "pass"
    assert result.name == "schema_completeness"


def test_check_schema_completeness_fails_on_empty_summary() -> None:
    """An empty summary field must produce a fail check."""

    proposal = _make_valid_proposal()
    proposal.summary = "   "
    result = check_schema_completeness(proposal)
    assert result.status == "fail"
    assert "summary" in result.detail


def test_check_schema_completeness_fails_on_empty_rationale() -> None:
    """An empty rationale field must produce a fail check."""

    proposal = _make_valid_proposal()
    proposal.rationale = ""
    result = check_schema_completeness(proposal)
    assert result.status == "fail"
    assert "rationale" in result.detail


def test_check_risk_file_consistency_passes_for_low_single_file() -> None:
    """Risk level 'low' with one target file should pass."""

    proposal = _make_valid_proposal(risk_level="low", target_files=["app/auth.py"])
    result = check_risk_file_consistency(proposal)
    assert result.status == "pass"


def test_check_risk_file_consistency_warns_on_mismatch() -> None:
    """Risk level 'low' with three files should trigger a warning."""

    proposal = _make_valid_proposal(
        risk_level="low",
        target_files=["app/auth.py", "app/session.py", "app/ui.py"],
    )
    result = check_risk_file_consistency(proposal)
    assert result.status == "warning"
    assert "low" in result.detail


def test_check_risk_file_consistency_passes_for_medium_two_files() -> None:
    """Risk level 'medium' with two target files should pass."""

    proposal = _make_valid_proposal(
        risk_level="medium",
        target_files=["app/auth.py", "app/session.py"],
    )
    result = check_risk_file_consistency(proposal)
    assert result.status == "pass"


def test_check_change_plan_coverage_passes_when_all_files_covered() -> None:
    """All target files having a change plan entry should pass."""

    result = check_change_plan_coverage(_make_valid_proposal())
    assert result.status == "pass"


def test_check_change_plan_coverage_fails_on_missing_entry() -> None:
    """A target file with no change plan entry must produce a fail check."""

    proposal = _make_valid_proposal(target_files=["app/auth.py"])
    proposal.target_files.append("app/missing.py")
    result = check_change_plan_coverage(proposal)
    assert result.status == "fail"
    assert "app/missing.py" in result.detail


def test_check_validation_focus_passes_when_populated() -> None:
    """A non-empty validation_focus list should pass."""

    result = check_validation_focus_populated(_make_valid_proposal())
    assert result.status == "pass"


def test_check_validation_focus_warns_when_empty() -> None:
    """An empty validation_focus list must produce a warning."""

    proposal = _make_valid_proposal()
    proposal.validation_focus = []
    result = check_validation_focus_populated(proposal)
    assert result.status == "warning"


def test_check_risk_notes_passes_when_present() -> None:
    """A non-empty risk_notes list should pass."""

    result = check_risk_notes_present(_make_valid_proposal())
    assert result.status == "pass"


def test_check_risk_notes_warns_when_empty() -> None:
    """An empty risk_notes list must produce a warning."""

    proposal = _make_valid_proposal()
    proposal.risk_notes = []
    result = check_risk_notes_present(proposal)
    assert result.status == "warning"


def test_run_structural_checks_returns_five_results() -> None:
    """run_structural_checks must always return exactly five check results."""

    checks = run_structural_checks(_make_valid_proposal())
    assert len(checks) == 5


def test_run_structural_checks_all_pass_on_valid_proposal() -> None:
    """Every check should pass for a fully valid proposal."""

    checks = run_structural_checks(_make_valid_proposal())
    statuses = [c.status for c in checks]
    assert all(s == "pass" for s in statuses), f"Unexpected statuses: {statuses}"


# ---------------------------------------------------------------------------
# compute_verdict unit tests
# ---------------------------------------------------------------------------


def test_compute_verdict_approved_when_all_checks_pass() -> None:
    """All-pass checks with low risk should yield approved with high confidence."""

    checks = run_structural_checks(_make_valid_proposal(risk_level="low"))
    verdict = compute_verdict(checks, "low")
    assert verdict.status == "approved"
    assert verdict.confidence == "high"
    assert verdict.checks_failed == 0
    assert verdict.checks_passed == 5


def test_compute_verdict_approved_high_risk_gets_low_confidence() -> None:
    """All-pass checks with high risk should yield approved but low confidence."""

    proposal = _make_valid_proposal(
        risk_level="high",
        target_files=["a.py", "b.py", "c.py", "d.py"],
    )
    checks = run_structural_checks(proposal)
    verdict = compute_verdict(checks, "high")
    assert verdict.status == "approved"
    assert verdict.confidence == "low"


def test_compute_verdict_needs_review_on_single_fail() -> None:
    """A single failed check should produce needs_review, not rejected."""

    proposal = _make_valid_proposal()
    proposal.summary = ""
    checks = run_structural_checks(proposal)
    verdict = compute_verdict(checks, proposal.risk_level)
    assert verdict.status == "needs_review"
    assert verdict.checks_failed == 1


def test_compute_verdict_rejected_on_multiple_fails() -> None:
    """Two or more failed checks should produce rejected."""

    proposal = _make_valid_proposal(target_files=["app/auth.py", "app/session.py"])
    proposal.summary = ""
    # change_plan only covers app/auth.py, so app/session.py has no entry → second fail
    proposal.change_plan = [proposal.change_plan[0]]
    checks = run_structural_checks(proposal)
    verdict = compute_verdict(checks, proposal.risk_level)
    assert verdict.status == "rejected"
    assert verdict.checks_failed >= 2


def test_compute_verdict_needs_review_when_only_warnings() -> None:
    """Warnings with no failures should yield needs_review."""

    proposal = _make_valid_proposal()
    proposal.validation_focus = []
    proposal.risk_notes = []
    checks = run_structural_checks(proposal)
    verdict = compute_verdict(checks, proposal.risk_level)
    assert verdict.status == "needs_review"
    assert verdict.checks_failed == 0
    assert verdict.checks_warned >= 1


# ---------------------------------------------------------------------------
# report_writer tool tests
# ---------------------------------------------------------------------------


def _make_final_report(issue_id: str = "ISSUE-010") -> FinalReport:
    """Return a minimal but structurally complete FinalReport for tool tests."""

    proposal = _make_valid_proposal(issue_id=issue_id)
    checks = run_structural_checks(proposal)
    verdict = compute_verdict(checks, proposal.risk_level)
    return FinalReport(
        issue_id=issue_id,
        patch_summary=proposal.summary,
        target_files=proposal.target_files,
        risk_level=proposal.risk_level,
        checks=checks,
        verdict=verdict,
        llm_assessment="All checks passed. Proposal is narrow and well-justified.",
        recommendation="Proceed with the patch.",
    )


def test_build_report_output_path_uses_issue_id(tmp_path: Path) -> None:
    """Output path should embed the issue id in the filename."""

    path = build_report_output_path("ISSUE-042", output_dir=str(tmp_path))
    assert path.name == "ISSUE-042_validation.json"


def test_build_report_output_path_raises_on_empty_issue_id() -> None:
    """An empty or whitespace-only issue_id must raise ValueError."""

    with pytest.raises(ValueError, match="non-empty"):
        build_report_output_path("   ")


def test_write_validation_report_creates_file(tmp_path: Path) -> None:
    """The tool must write a JSON file to the specified output directory."""

    report = _make_final_report()
    artifact = write_validation_report(report, output_dir=str(tmp_path))

    assert Path(artifact.artifact_path).exists()
    assert artifact.report.issue_id == "ISSUE-010"


def test_write_validation_report_produces_valid_json(tmp_path: Path) -> None:
    """The written file must be valid JSON containing the issue_id key."""

    report = _make_final_report("ISSUE-011")
    artifact = write_validation_report(report, output_dir=str(tmp_path))

    content = json.loads(Path(artifact.artifact_path).read_text(encoding="utf-8"))
    assert content["issue_id"] == "ISSUE-011"
    assert "verdict" in content
    assert "checks" in content


def test_write_validation_report_preserves_verdict_status(tmp_path: Path) -> None:
    """Verdict status must survive serialization round-trip."""

    report = _make_final_report()
    artifact = write_validation_report(report, output_dir=str(tmp_path))

    content = json.loads(Path(artifact.artifact_path).read_text(encoding="utf-8"))
    assert content["verdict"]["status"] == report.verdict.status


# ---------------------------------------------------------------------------
# ValidationAgent integration tests
# ---------------------------------------------------------------------------


def test_validation_agent_raises_without_patch_output() -> None:
    """The agent must raise ValueError when patch_agent_output is absent."""

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-020",
            title="Missing patch output",
            description="No patch was produced upstream.",
        )
    )
    agent = ValidationAgent()
    with pytest.raises(ValueError, match="patch_agent_output"):
        agent.run(state)


def test_validation_agent_writes_report_artifact(tmp_path: Path) -> None:
    """A full agent run must produce a JSON artifact on disk."""

    state = _make_valid_state()
    agent = ValidationAgent(output_dir=str(tmp_path))
    updated = agent.run(state)

    assert updated.validation_output is not None
    assert Path(updated.validation_output.artifact_path).exists()


def test_validation_agent_populates_state_validation_output(tmp_path: Path) -> None:
    """After run(), state.validation_output must be a ValidationArtifact."""

    state = _make_valid_state()
    agent = ValidationAgent(output_dir=str(tmp_path))
    updated = agent.run(state)

    assert isinstance(updated.validation_output, ValidationArtifact)
    assert updated.validation_output.report.issue_id == "ISSUE-010"


def test_validation_agent_approved_for_clean_proposal(tmp_path: Path) -> None:
    """A structurally valid low-risk proposal should produce an approved verdict."""

    state = _make_valid_state(_make_valid_proposal(risk_level="low"))
    agent = ValidationAgent(output_dir=str(tmp_path))
    updated = agent.run(state)

    assert updated.validation_output is not None
    assert updated.validation_output.report.verdict.status == "approved"


def test_validation_agent_needs_review_for_flawed_proposal(tmp_path: Path) -> None:
    """A proposal with a structural fail should not be approved."""

    proposal = _make_valid_proposal()
    proposal.summary = ""
    state = _make_valid_state(proposal)
    agent = ValidationAgent(output_dir=str(tmp_path))
    updated = agent.run(state)

    assert updated.validation_output is not None
    assert updated.validation_output.report.verdict.status in (
        "needs_review",
        "rejected",
    )


def test_validation_agent_accepts_fake_verdict_generator(tmp_path: Path) -> None:
    """The agent must delegate to an injected generator and capture its output."""

    fake = FakeVerdictGenerator()
    state = _make_valid_state()
    agent = ValidationAgent(output_dir=str(tmp_path), verdict_generator=fake)
    updated = agent.run(state)

    assert fake.last_state is state
    assert fake.last_checks is not None
    assert len(fake.last_checks) == 5
    assert updated.validation_output is not None
    assert updated.validation_output.report.verdict.status == "approved"
    assert updated.validation_output.report.llm_assessment.startswith("Fake assessment")


def test_validation_agent_falls_back_when_generator_raises(tmp_path: Path) -> None:
    """When the generator raises and allow_fallback is True the run must succeed."""

    state = _make_valid_state()
    agent = ValidationAgent(
        output_dir=str(tmp_path),
        verdict_generator=FailingVerdictGenerator(),
        allow_fallback=True,
    )
    updated = agent.run(state)
    assert updated.validation_output is not None


def test_validation_agent_raises_when_fallback_disabled(tmp_path: Path) -> None:
    """When allow_fallback is False a generator failure must propagate."""

    state = _make_valid_state()
    agent = ValidationAgent(
        output_dir=str(tmp_path),
        verdict_generator=FailingVerdictGenerator(),
        allow_fallback=False,
    )
    with pytest.raises(RuntimeError, match="Simulated Ollama"):
        agent.run(state)


def test_validation_agent_report_contains_all_five_checks(tmp_path: Path) -> None:
    """The written report must include results for all five structural checks."""

    state = _make_valid_state()
    agent = ValidationAgent(output_dir=str(tmp_path))
    updated = agent.run(state)

    content = json.loads(
        Path(updated.validation_output.artifact_path).read_text(encoding="utf-8")
    )
    assert len(content["checks"]) == 5


def test_validation_agent_report_check_names_are_unique(tmp_path: Path) -> None:
    """Each structural check should appear exactly once in the report."""

    state = _make_valid_state()
    agent = ValidationAgent(output_dir=str(tmp_path))
    updated = agent.run(state)

    names = [c.name for c in updated.validation_output.report.checks]
    assert len(names) == len(set(names)), "Duplicate check names found in report."
