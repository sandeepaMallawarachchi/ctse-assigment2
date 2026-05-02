from __future__ import annotations

"""Tests for the Triage Agent and issue parser tool."""

import json
from pathlib import Path

from agents.triage_agent.agent import TriageAgent
from orchestrator.state import IssueContext, PatchWorkflowState
from tools.triage_tools.issue_parser import (
    classify_issue_type,
    estimate_priority,
    parse_issue,
)


def test_classify_issue_type_detects_bug() -> None:
    """Bug-like issue wording should be classified as a bug."""

    result = classify_issue_type(
        title="Fix login button spinner not stopping",
        description="The button stays stuck after a failed login attempt.",
    )

    assert result == "bug"


def test_estimate_priority_detects_medium_severity() -> None:
    """Failure-oriented issue wording should produce medium priority."""

    result = estimate_priority(
        title="Fix login button spinner not stopping",
        description="The button remains stuck after a failed login attempt.",
    )

    assert result == "medium"


def test_parse_issue_extracts_search_keywords() -> None:
    """The parser should produce triage keywords for later analysis."""

    summary = parse_issue(
        IssueContext(
            issue_id="ISSUE-400",
            title="Fix login button spinner not stopping",
            description="The button remains stuck after a failed login attempt.",
            expected_behavior="The spinner should stop after failure.",
        )
    )

    assert "login" in summary.search_keywords
    assert "spinner" in summary.search_keywords


def test_triage_agent_writes_artifact(tmp_path: Path) -> None:
    """The triage agent should persist its structured output to disk."""

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-401",
            title="Fix login button spinner not stopping",
            description="The button remains stuck after a failed login attempt.",
            expected_behavior="The spinner should stop after failure.",
        )
    )

    agent = TriageAgent(output_dir=str(tmp_path))
    updated_state = agent.run(state)

    assert updated_state.triage_output is not None
    artifact_path = Path(updated_state.triage_output.artifact_path)
    assert artifact_path.exists()

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["issue_id"] == "ISSUE-401"
    assert payload["issue_type"] == "bug"
