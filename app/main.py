"""Application entrypoint for running the local MAS prototype.

This file will later initialize configuration, shared state, and the
orchestrator entry flow. For now it provides a small patch-agent demo.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Optional
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.analysis_agent.agent import (
    CodebaseAnalysisAgent,
    OllamaAnalysisSummaryGenerator,
)
from agents.analysis_agent.schema import AnalysisArtifact
from agents.patch_agent.agent import (
    OllamaPatchProposalGenerator,
    PatchGenerationAgent,
)
from agents.triage_agent.agent import OllamaTriageSummaryGenerator, TriageAgent
from agents.validation_agent.agent import (
    OllamaValidationVerdictGenerator,
    ValidationAgent,
)
from app.config import AppConfig
from orchestrator.graph import run_workflow
from orchestrator.state import IssueContext, PatchWorkflowState, RepositoryFinding


def configure_logging(config: AppConfig) -> None:
    """Configure console and file logging for the local demo run."""

    log_path = Path(config.execution_log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the local agent runner."""

    parser = argparse.ArgumentParser(description="Run a local agent demo.")
    parser.add_argument(
        "--run",
        choices=["triage", "analysis", "patch", "validation", "full"],
        help="Choose a single agent or the currently connected full flow.",
    )
    parser.add_argument(
        "--issue-file",
        default="data/issues/sample_issue.json",
        help="Path to a JSON issue payload file.",
    )
    parser.add_argument(
        "--repo-root",
        default="data/repo_mock",
        help="Local repository path for analysis-focused runs.",
    )
    parser.add_argument(
        "--analysis-artifact",
        default=None,
        help="Optional analysis artifact JSON path to use for patch-agent runs.",
    )
    parser.add_argument(
        "--code-file",
        default=None,
        help="Optional local code file path to focus the agents on.",
    )
    return parser.parse_args()


def prompt_for_run_mode() -> str:
    """Prompt the user to choose a runnable mode from the terminal menu."""

    print("Select what to run:")
    print("1. Triage Agent")
    print("2. Codebase Analysis Agent")
    print("3. Patch Generation Agent")
    print("4. Validation & Report Agent")
    print("5. Full Flow (Triage -> Analysis -> Patch -> Validation)")

    option_to_mode = {
        "1": "triage",
        "2": "analysis",
        "3": "patch",
        "4": "validation",
        "5": "full",
    }

    while True:
        selected_option = input("Enter option number: ").strip()
        if selected_option in option_to_mode:
            return option_to_mode[selected_option]
        print("Invalid option. Please enter 1, 2, 3, 4, or 5.")


def build_demo_state(
    issue_file: str,
    repo_root: str,
    code_file: Optional[str] = None,
) -> PatchWorkflowState:
    """Load a sample issue and create mock analysis findings for the patch demo."""

    sample_issue_path = Path(issue_file)
    issue_payload = json.loads(sample_issue_path.read_text(encoding="utf-8"))

    return build_state_from_issue_payload(
        issue_payload=issue_payload,
        repo_root=repo_root,
        code_file=code_file,
    )


def build_state_from_issue_payload(
    issue_payload: dict[str, Any],
    repo_root: str,
    code_file: Optional[str] = None,
) -> PatchWorkflowState:
    """Build shared workflow state from an in-memory issue payload."""

    return PatchWorkflowState(
        issue=IssueContext(**issue_payload),
        run_id=f"RUN-{uuid.uuid4().hex[:8].upper()}",
        repository_root=repo_root,
        target_code_file=code_file,
    )


def _triage_artifact_to_dict(state: PatchWorkflowState) -> dict[str, Any] | None:
    """Serialize triage output into a UI-friendly dictionary."""

    if state.triage_output is None:
        return None
    summary = state.triage_output.summary
    return {
        "issue_id": summary.issue_id,
        "issue_type": summary.issue_type,
        "priority": summary.priority,
        "normalized_title": summary.normalized_title,
        "normalized_description": summary.normalized_description,
        "expected_behavior": summary.expected_behavior,
        "search_keywords": summary.search_keywords,
        "summary": summary.summary,
        "artifact_path": state.triage_output.artifact_path,
    }


def _analysis_artifact_to_dict(state: PatchWorkflowState) -> dict[str, Any] | None:
    """Serialize analysis output into a UI-friendly dictionary."""

    if state.analysis_output is None:
        return None
    summary = state.analysis_output.summary
    return {
        "issue_id": summary.issue_id,
        "repo_path": summary.repo_path,
        "search_terms": summary.search_terms,
        "findings": [
            {
                "file_path": finding.file_path,
                "snippet": finding.snippet,
                "reason": finding.reason,
                "line_start": finding.line_start,
                "line_end": finding.line_end,
            }
            for finding in summary.findings
        ],
        "summary": summary.summary,
        "artifact_path": state.analysis_output.artifact_path,
    }


def _patch_artifact_to_dict(state: PatchWorkflowState) -> dict[str, Any] | None:
    """Serialize patch output into a UI-friendly dictionary."""

    if state.patch_agent_output is None:
        return None
    proposal = state.patch_agent_output.proposal
    return {
        "issue_id": proposal.issue_id,
        "summary": proposal.summary,
        "target_files": proposal.target_files,
        "change_plan": [
            {
                "file_path": change.file_path,
                "change_summary": change.change_summary,
                "evidence": change.evidence,
            }
            for change in proposal.change_plan
        ],
        "rationale": proposal.rationale,
        "risk_level": proposal.risk_level,
        "risk_notes": proposal.risk_notes,
        "validation_focus": proposal.validation_focus,
        "artifact_path": state.patch_agent_output.artifact_path,
        "patch_draft_path": state.patch_agent_output.patch_draft_path,
        "patch_draft": state.patch_agent_output.patch_draft,
    }


def _validation_artifact_to_dict(state: PatchWorkflowState) -> dict[str, Any] | None:
    """Serialize validation output into a UI-friendly dictionary."""

    if state.validation_output is None:
        return None
    report = state.validation_output.report
    verdict = report.verdict
    return {
        "issue_id": report.issue_id,
        "patch_summary": report.patch_summary,
        "target_files": report.target_files,
        "risk_level": report.risk_level,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
            }
            for check in report.checks
        ],
        "verdict": {
            "status": verdict.status,
            "confidence": verdict.confidence,
            "rationale": verdict.rationale,
            "checks_passed": verdict.checks_passed,
            "checks_failed": verdict.checks_failed,
            "checks_warned": verdict.checks_warned,
        },
        "llm_assessment": report.llm_assessment,
        "recommendation": report.recommendation,
        "artifact_path": state.validation_output.artifact_path,
    }


def build_result_payload(
    run_mode: str,
    state: PatchWorkflowState,
) -> dict[str, Any]:
    """Build a structured result payload for CLI-independent consumers."""

    return {
        "run_mode": run_mode,
        "run_id": state.run_id,
        "execution_trace": state.execution_trace,
        "issue": {
            "issue_id": state.issue.issue_id,
            "title": state.issue.title,
            "description": state.issue.description,
            "expected_behavior": state.issue.expected_behavior,
        },
        "repository_root": state.repository_root,
        "target_code_file": state.target_code_file,
        "triage": _triage_artifact_to_dict(state),
        "analysis": _analysis_artifact_to_dict(state),
        "patch": _patch_artifact_to_dict(state),
        "validation": _validation_artifact_to_dict(state),
    }


def execute_run_mode(
    run_mode: str,
    state: PatchWorkflowState,
    config: AppConfig,
    analysis_artifact_path: Optional[str] = None,
    emit_console: bool = True,
) -> PatchWorkflowState:
    """Execute a selected agent or flow and return the updated state."""

    logger = logging.getLogger(__name__)

    if run_mode == "triage":
        updated_state = run_workflow(
            initial_state=state,
            config=config,
            build_triage_agent=build_triage_agent,
            build_analysis_agent=build_analysis_agent,
            build_patch_agent=build_patch_agent,
            build_validation_agent=build_validation_agent,
            run_mode="triage",
        )
        if emit_console:
            _print_triage_summary(updated_state)
        return updated_state

    if run_mode == "analysis":
        updated_state = run_workflow(
            initial_state=state,
            config=config,
            build_triage_agent=build_triage_agent,
            build_analysis_agent=build_analysis_agent,
            build_patch_agent=build_patch_agent,
            build_validation_agent=build_validation_agent,
            run_mode="analysis",
        )
        if emit_console:
            _print_analysis_summary(updated_state)
        return updated_state

    if run_mode in {"patch", "validation"} and analysis_artifact_path:
        logger.info(
            "Application loading analysis artifact for run mode=%s path=%s",
            run_mode,
            analysis_artifact_path,
        )
        state = apply_analysis_artifact_to_state(state, analysis_artifact_path)

    if run_mode in {"patch", "validation", "full"}:
        logger.info(
            "Application invoking LangGraph workflow run_mode=%s run_id=%s",
            run_mode,
            state.run_id,
        )
        updated_state = run_workflow(
            initial_state=state,
            config=config,
            build_triage_agent=build_triage_agent,
            build_analysis_agent=build_analysis_agent,
            build_patch_agent=build_patch_agent,
            build_validation_agent=build_validation_agent,
            run_mode=run_mode,
        )
        if emit_console:
            if run_mode == "patch":
                _print_analysis_summary(updated_state)
                _print_patch_summary(updated_state)
            elif run_mode == "validation":
                _print_analysis_summary(updated_state)
                _print_patch_summary(updated_state)
                _print_validation_summary(updated_state)
            else:
                _print_triage_summary(updated_state)
                _print_analysis_summary(updated_state)
                _print_patch_summary(updated_state)
                _print_validation_summary(updated_state)
        return updated_state

    return state


def _load_analysis_artifact(artifact_path: str) -> AnalysisArtifact:
    """Load a serialized analysis artifact from disk.

    Supports both the newer wrapped `AnalysisArtifact` JSON shape and the
    existing summary-only artifact shape already written by this project.
    """

    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    if not (
        isinstance(payload.get("summary"), dict)
        and "artifact_path" in payload
    ):
        payload = {
            "summary": payload,
            "artifact_path": artifact_path,
        }
    if hasattr(AnalysisArtifact, "model_validate"):
        return AnalysisArtifact.model_validate(payload)
    return AnalysisArtifact.parse_obj(payload)


def apply_analysis_artifact_to_state(
    state: PatchWorkflowState,
    artifact_path: str,
) -> PatchWorkflowState:
    """Populate shared state from a previously written analysis artifact.

    Args:
        state: Workflow state that will be updated for the patch stage.
        artifact_path: Path to a serialized `AnalysisArtifact` JSON file.

    Returns:
        Updated state containing analysis output and repository findings.
    """

    artifact = _load_analysis_artifact(artifact_path)
    state.repository_root = artifact.summary.repo_path
    state.analysis_output = artifact
    state.repository_findings = [
        RepositoryFinding(
            file_path=finding.file_path,
            snippet=finding.snippet,
            reason=finding.reason,
            line_start=finding.line_start,
            line_end=finding.line_end,
        )
        for finding in artifact.summary.findings
    ]
    return state


def build_analysis_agent(config: AppConfig) -> CodebaseAnalysisAgent:
    """Create the analysis agent with Ollama support and safe fallback."""

    summary_generator = None
    if config.use_ollama_for_analysis_agent:
        summary_generator = OllamaAnalysisSummaryGenerator(
            model_name=config.analysis_agent_model,
            base_url=config.ollama_base_url,
        )

    return CodebaseAnalysisAgent(
        output_dir=config.analysis_output_dir,
        summary_generator=summary_generator,
        allow_fallback=config.allow_analysis_fallback,
    )


def build_triage_agent(config: AppConfig) -> TriageAgent:
    """Create the triage agent with Ollama support and safe fallback."""

    summary_generator = None
    if config.use_ollama_for_triage_agent:
        summary_generator = OllamaTriageSummaryGenerator(
            model_name=config.triage_agent_model,
            base_url=config.ollama_base_url,
        )

    return TriageAgent(
        output_dir=config.triage_output_dir,
        summary_generator=summary_generator,
        allow_fallback=config.allow_triage_fallback,
    )


def build_patch_agent(config: AppConfig) -> PatchGenerationAgent:
    """Create the patch agent with Ollama support and safe fallback."""

    proposal_generator = None
    if config.use_ollama_for_patch_agent:
        proposal_generator = OllamaPatchProposalGenerator(
            model_name=config.patch_agent_model,
            base_url=config.ollama_base_url,
        )

    return PatchGenerationAgent(
        output_dir=config.patch_output_dir,
        proposal_generator=proposal_generator,
        allow_fallback=config.allow_patch_fallback,
    )


def build_validation_agent(config: AppConfig) -> ValidationAgent:
    """Create the validation agent with Ollama support and safe fallback."""

    verdict_generator = None
    if config.use_ollama_for_validation_agent:
        verdict_generator = OllamaValidationVerdictGenerator(
            model_name=config.validation_agent_model,
            base_url=config.ollama_base_url,
        )

    return ValidationAgent(
        output_dir=config.validation_output_dir,
        verdict_generator=verdict_generator,
        allow_fallback=config.allow_validation_fallback,
    )


def run_analysis_stage(
    state: PatchWorkflowState,
    config: AppConfig,
) -> PatchWorkflowState:
    """Run the Codebase Analysis Agent and print a short summary."""

    agent = build_analysis_agent(config)
    updated_state = agent.run(state)
    artifact = updated_state.analysis_output
    assert artifact is not None

    print("Codebase Analysis Agent demo completed")
    print(f"Issue ID: {artifact.summary.issue_id}")
    print(f"Repository root: {artifact.summary.repo_path}")
    if state.target_code_file:
        print(f"Target code file: {state.target_code_file}")
    print(f"Findings count: {len(artifact.summary.findings)}")
    print(f"Artifact path: {artifact.artifact_path}")
    return updated_state


def run_triage_stage(
    state: PatchWorkflowState,
    config: AppConfig,
) -> PatchWorkflowState:
    """Run the Triage Agent and print a short summary."""

    agent = build_triage_agent(config)
    updated_state = agent.run(state)
    artifact = updated_state.triage_output
    assert artifact is not None

    print("Triage Agent demo completed")
    print(f"Issue ID: {artifact.summary.issue_id}")
    print(f"Issue type: {artifact.summary.issue_type}")
    print(f"Priority: {artifact.summary.priority}")
    print(f"Keywords: {', '.join(artifact.summary.search_keywords)}")
    print(f"Artifact path: {artifact.artifact_path}")
    return updated_state


def run_patch_stage(
    state: PatchWorkflowState,
    config: AppConfig,
) -> PatchWorkflowState:
    """Run the Patch Generation Agent and print a short summary."""

    agent = build_patch_agent(config)
    updated_state = agent.run(state)
    artifact = updated_state.patch_agent_output
    assert artifact is not None

    print("Patch Generation Agent demo completed")
    print(f"Issue ID: {artifact.proposal.issue_id}")
    if state.target_code_file:
        print(f"Target code file: {state.target_code_file}")
    print(f"Target files: {', '.join(artifact.proposal.target_files)}")
    print(f"Risk level: {artifact.proposal.risk_level}")
    print(f"Artifact path: {artifact.artifact_path}")
    print(f"Patch draft path: {artifact.patch_draft_path}")
    return updated_state


def run_validation_stage(
    state: PatchWorkflowState,
    config: AppConfig,
) -> PatchWorkflowState:
    """Run the Validation & Report Agent and print a short summary."""

    agent = build_validation_agent(config)
    updated_state = agent.run(state)
    artifact = updated_state.validation_output
    assert artifact is not None
    report = artifact.report
    verdict = report.verdict

    print("Validation & Report Agent completed")
    print(f"Issue ID: {report.issue_id}")
    if state.target_code_file:
        print(f"Target code file: {state.target_code_file}")
    print(f"Verdict: {verdict.status} (confidence: {verdict.confidence})")
    print(
        f"Checks: {verdict.checks_passed} passed, "
        f"{verdict.checks_failed} failed, {verdict.checks_warned} warned"
    )
    print(f"Assessment: {report.llm_assessment}")
    print(f"Recommendation: {report.recommendation}")
    print(f"Report path: {artifact.artifact_path}")
    return updated_state


def _print_triage_summary(state: PatchWorkflowState) -> None:
    """Print triage output without re-running the agent."""

    artifact = state.triage_output
    assert artifact is not None
    print("Triage Agent demo completed")
    print(f"Issue ID: {artifact.summary.issue_id}")
    print(f"Issue type: {artifact.summary.issue_type}")
    print(f"Priority: {artifact.summary.priority}")
    print(f"Keywords: {', '.join(artifact.summary.search_keywords)}")
    print(f"Artifact path: {artifact.artifact_path}")


def _print_analysis_summary(state: PatchWorkflowState) -> None:
    """Print analysis output without re-running the agent."""

    artifact = state.analysis_output
    assert artifact is not None
    print("Codebase Analysis Agent demo completed")
    print(f"Issue ID: {artifact.summary.issue_id}")
    print(f"Repository root: {artifact.summary.repo_path}")
    if state.target_code_file:
        print(f"Target code file: {state.target_code_file}")
    print(f"Findings count: {len(artifact.summary.findings)}")
    print(f"Artifact path: {artifact.artifact_path}")


def _print_patch_summary(state: PatchWorkflowState) -> None:
    """Print patch output without re-running the agent."""

    artifact = state.patch_agent_output
    assert artifact is not None
    print("Patch Generation Agent demo completed")
    print(f"Issue ID: {artifact.proposal.issue_id}")
    if state.target_code_file:
        print(f"Target code file: {state.target_code_file}")
    print(f"Target files: {', '.join(artifact.proposal.target_files)}")
    print(f"Risk level: {artifact.proposal.risk_level}")
    print(f"Artifact path: {artifact.artifact_path}")
    print(f"Patch draft path: {artifact.patch_draft_path}")


def _print_validation_summary(state: PatchWorkflowState) -> None:
    """Print validation output without re-running the agent."""

    artifact = state.validation_output
    assert artifact is not None
    report = artifact.report
    verdict = report.verdict
    print("Validation & Report Agent completed")
    print(f"Issue ID: {report.issue_id}")
    if state.target_code_file:
        print(f"Target code file: {state.target_code_file}")
    print(f"Verdict: {verdict.status} (confidence: {verdict.confidence})")
    print(
        f"Checks: {verdict.checks_passed} passed, "
        f"{verdict.checks_failed} failed, {verdict.checks_warned} warned"
    )
    print(f"Assessment: {report.llm_assessment}")
    print(f"Recommendation: {report.recommendation}")
    print(f"Report path: {artifact.artifact_path}")


def main() -> None:
    """Run a selected agent or connected demo flow from the project root."""

    args = parse_args()
    run_mode = args.run or prompt_for_run_mode()
    config = AppConfig()
    configure_logging(config)
    logger = logging.getLogger(__name__)
    logger.info(
        "Application startup for local agent runner mode=%s",
        run_mode,
    )
    state = build_demo_state(
        issue_file=args.issue_file,
        repo_root=args.repo_root,
        code_file=args.code_file,
    )
    updated_state = execute_run_mode(
        run_mode=run_mode,
        state=state,
        config=config,
        analysis_artifact_path=args.analysis_artifact,
        emit_console=True,
    )
    result_payload = build_result_payload(run_mode, updated_state)
    logger.info(
        "Application completed run mode=%s issue_id=%s",
        run_mode,
        result_payload["issue"]["issue_id"],
    )


if __name__ == "__main__":
    main()
