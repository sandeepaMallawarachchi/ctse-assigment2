from __future__ import annotations

"""Tests for the LangGraph-backed MAS workflow."""

import json
from pathlib import Path

from app.config import AppConfig
from app.main import (
    apply_analysis_artifact_to_state,
    build_analysis_agent,
    build_patch_agent,
    build_state_from_issue_payload,
    build_triage_agent,
    build_validation_agent,
)
from orchestrator.graph import run_workflow


def _make_test_config(tmp_path: Path) -> AppConfig:
    """Create a config object that uses deterministic local fallbacks."""

    config = AppConfig()
    config.use_ollama_for_triage_agent = False
    config.use_ollama_for_analysis_agent = False
    config.use_ollama_for_patch_agent = False
    config.use_ollama_for_validation_agent = False
    config.triage_output_dir = str(tmp_path / "reports")
    config.analysis_output_dir = str(tmp_path / "reports")
    config.validation_output_dir = str(tmp_path / "reports")
    config.patch_output_dir = str(tmp_path / "patches")
    config.execution_log_path = str(tmp_path / "execution.log")
    return config


def test_langgraph_full_workflow_populates_all_agent_outputs(tmp_path: Path) -> None:
    """The compiled graph should run the full connected MAS flow."""

    state = build_state_from_issue_payload(
        issue_payload={
            "issue_id": "ISSUE-500",
            "title": "Fix login spinner not stopping",
            "description": "Spinner stays active after a failed login.",
            "expected_behavior": "Spinner should stop after failed authentication.",
        },
        repo_root="data/repo_mock",
    )
    config = _make_test_config(tmp_path)

    updated_state = run_workflow(
        initial_state=state,
        config=config,
        build_triage_agent=build_triage_agent,
        build_analysis_agent=build_analysis_agent,
        build_patch_agent=build_patch_agent,
        build_validation_agent=build_validation_agent,
        run_mode="full",
    )

    assert updated_state.triage_output is not None
    assert updated_state.analysis_output is not None
    assert updated_state.patch_agent_output is not None
    assert updated_state.validation_output is not None
    assert updated_state.execution_trace == ["triage", "analysis", "patch", "validation"]


def test_langgraph_patch_workflow_can_start_from_analysis_artifact(tmp_path: Path) -> None:
    """Patch graph should skip re-analysis when prior analysis state already exists."""

    artifact_path = tmp_path / "analysis.json"
    artifact_payload = {
        "summary": {
            "issue_id": "ISSUE-501",
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

    state = build_state_from_issue_payload(
        issue_payload={
            "issue_id": "ISSUE-501",
            "title": "Fix login spinner",
            "description": "Spinner stays active after failure.",
        },
        repo_root="data/repo_mock",
    )
    state = apply_analysis_artifact_to_state(state, str(artifact_path))
    config = _make_test_config(tmp_path)

    updated_state = run_workflow(
        initial_state=state,
        config=config,
        build_triage_agent=build_triage_agent,
        build_analysis_agent=build_analysis_agent,
        build_patch_agent=build_patch_agent,
        build_validation_agent=build_validation_agent,
        run_mode="patch",
    )

    assert updated_state.patch_agent_output is not None
    assert updated_state.execution_trace == ["patch"]
