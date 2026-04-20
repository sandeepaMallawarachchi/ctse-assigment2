from __future__ import annotations

"""Tests for the Codebase Analysis Agent and search tool."""

import json
from pathlib import Path

from agents.analysis_agent.agent import CodebaseAnalysisAgent
from orchestrator.state import IssueContext, PatchWorkflowState
from tools.analysis_tools.code_search import derive_search_terms, search_repository


def test_derive_search_terms_extracts_keywords() -> None:
    """Issue text should produce stable search keywords."""

    terms = derive_search_terms(
        title="Fix login button spinner not stopping",
        description="The login spinner stays active after failed authentication.",
        expected_behavior="Spinner should stop after failure.",
    )

    assert "login" in terms
    assert "spinner" in terms


def test_search_repository_returns_mock_repo_findings() -> None:
    """The custom search tool should find relevant files in the mock repo."""

    results = search_repository(
        repo_root="data/repo_mock",
        search_terms=["login", "spinner", "failed"],
    )

    assert results
    assert any(result.finding.file_path == "src/auth/login_handler.py" for result in results)
    assert any(result.finding.file_path == "src/ui/login_form.py" for result in results)

    auth_result = next(
        result for result in results if result.finding.file_path == "src/auth/login_handler.py"
    )
    ui_result = next(
        result for result in results if result.finding.file_path == "src/ui/login_form.py"
    )

    assert "if login_failed:" in auth_result.finding.snippet
    assert "submit_button = {" in ui_result.finding.snippet


def test_codebase_analysis_agent_writes_analysis_artifact(tmp_path: Path) -> None:
    """The analysis agent should populate shared state and persist its output."""

    state = PatchWorkflowState(
        issue=IssueContext(
            issue_id="ISSUE-100",
            title="Fix login button spinner not stopping",
            description="Spinner stays active after a failed login.",
            expected_behavior="Spinner should stop after failed authentication.",
        ),
        repository_root="data/repo_mock",
    )

    agent = CodebaseAnalysisAgent(output_dir=str(tmp_path))
    updated_state = agent.run(state)

    assert updated_state.analysis_output is not None
    assert updated_state.repository_findings
    artifact_path = Path(updated_state.analysis_output.artifact_path)
    assert artifact_path.exists()

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["issue_id"] == "ISSUE-100"
    assert payload["repo_path"] == "data/repo_mock"
