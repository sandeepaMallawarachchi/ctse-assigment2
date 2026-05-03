from __future__ import annotations

"""Lightweight evaluation runner for the LangGraph MAS workflow.

This script executes a few representative issue scenarios and writes a compact
JSON summary that can be cited in the assignment report as local evaluation
evidence.
"""

import json
from pathlib import Path

from app.config import AppConfig
from app.main import (
    build_analysis_agent,
    build_patch_agent,
    build_state_from_issue_payload,
    build_triage_agent,
    build_validation_agent,
)
from orchestrator.graph import run_workflow


def build_evaluation_config() -> AppConfig:
    """Create a deterministic config for repeatable local evaluation."""

    config = AppConfig()
    config.use_ollama_for_triage_agent = False
    config.use_ollama_for_analysis_agent = False
    config.use_ollama_for_patch_agent = False
    config.use_ollama_for_validation_agent = False
    return config


def evaluate_case(config: AppConfig, issue_payload: dict[str, str]) -> dict[str, object]:
    """Run one full workflow case and return compact evaluation metrics."""

    state = build_state_from_issue_payload(
        issue_payload=issue_payload,
        repo_root="data/repo_mock",
    )
    updated_state = run_workflow(
        initial_state=state,
        config=config,
        build_triage_agent=build_triage_agent,
        build_analysis_agent=build_analysis_agent,
        build_patch_agent=build_patch_agent,
        build_validation_agent=build_validation_agent,
        run_mode="full",
    )

    triage = updated_state.triage_output.summary if updated_state.triage_output else None
    analysis = updated_state.analysis_output.summary if updated_state.analysis_output else None
    patch = updated_state.patch_agent_output.proposal if updated_state.patch_agent_output else None
    validation = updated_state.validation_output.report if updated_state.validation_output else None

    return {
        "issue_id": updated_state.issue.issue_id,
        "execution_trace": updated_state.execution_trace,
        "triage_issue_type": triage.issue_type if triage else None,
        "analysis_findings": len(analysis.findings) if analysis else 0,
        "patch_target_files": patch.target_files if patch else [],
        "validation_status": validation.verdict.status if validation else None,
        "checks_passed": validation.verdict.checks_passed if validation else 0,
        "checks_failed": validation.verdict.checks_failed if validation else 0,
        "checks_warned": validation.verdict.checks_warned if validation else 0,
    }


def main() -> None:
    """Run a small local evaluation set and write a summary artifact."""

    config = build_evaluation_config()
    cases = [
        {
            "issue_id": "EVAL-001",
            "title": "Fix login button spinner not stopping",
            "description": "The login spinner stays active after a failed authentication attempt.",
            "expected_behavior": "The spinner should stop after a failed login.",
        },
        {
            "issue_id": "EVAL-002",
            "title": "Fix incorrect retry state after failed request",
            "description": "The retry button remains disabled after an API failure.",
            "expected_behavior": "Retry should become active again after failure.",
        },
    ]

    results = [evaluate_case(config, case) for case in cases]
    summary = {
        "evaluation_cases": len(results),
        "results": results,
        "all_traces_complete": all(
            result["execution_trace"] == ["triage", "analysis", "patch", "validation"]
            for result in results
        ),
    }

    output_path = Path("outputs/reports/evaluation_summary.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Evaluation summary written to: {output_path}")


if __name__ == "__main__":
    main()
