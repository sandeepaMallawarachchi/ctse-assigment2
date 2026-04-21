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
from agents.validation_agent.agent import (
    OllamaValidationVerdictGenerator,
    ValidationAgent,
)
from app.config import AppConfig
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
        choices=["analysis", "patch", "validation", "full"],
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
    return parser.parse_args()


def prompt_for_run_mode() -> str:
    """Prompt the user to choose a runnable mode from the terminal menu."""

    print("Select what to run:")
    print("1. Codebase Analysis Agent")
    print("2. Patch Generation Agent")
    print("3. Validation & Report Agent")
    print("4. Full Flow (Analysis -> Patch -> Validation)")

    option_to_mode = {
        "1": "analysis",
        "2": "patch",
        "3": "validation",
        "4": "full",
    }

    while True:
        selected_option = input("Enter option number: ").strip()
        if selected_option in option_to_mode:
            return option_to_mode[selected_option]
        print("Invalid option. Please enter 1, 2, 3, or 4.")


def build_demo_state(
    issue_file: str,
    repo_root: str,
) -> PatchWorkflowState:
    """Load a sample issue and create mock analysis findings for the patch demo."""

    sample_issue_path = Path(issue_file)
    issue_payload = json.loads(sample_issue_path.read_text(encoding="utf-8"))

    return PatchWorkflowState(
        issue=IssueContext(**issue_payload),
        repository_root=repo_root,
        repository_findings=[
            RepositoryFinding(
                file_path="src/auth/login_handler.py",
                snippet="if login_failed: spinner = True",
                reason="Failure handling appears to leave the loading spinner active.",
                line_start=18,
                line_end=26,
            ),
            RepositoryFinding(
                file_path="src/ui/login_form.py",
                snippet="submit_button.loading = state.is_submitting",
                reason="The login form controls how the button loading state is rendered.",
                line_start=41,
                line_end=55,
            ),
        ],
    )


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
    print(f"Findings count: {len(artifact.summary.findings)}")
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
    print(f"Target files: {', '.join(artifact.proposal.target_files)}")
    print(f"Risk level: {artifact.proposal.risk_level}")
    print(f"Artifact path: {artifact.artifact_path}")
    print(f"Patch draft path: {artifact.patch_draft_path}")
    return updated_state


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


def run_validation_stage(
    state: PatchWorkflowState,
    config: AppConfig,
) -> PatchWorkflowState:
    """Run the Validation & Report Agent and print a short summary."""

    agent = build_validation_agent(config)
    updated_state = agent.run(state)
    report = updated_state.validation_output.report
    verdict = report.verdict

    print("Validation & Report Agent completed")
    print(f"Issue ID: {report.issue_id}")
    print(f"Verdict  : {verdict.status} (confidence: {verdict.confidence})")
    print(f"Checks   : {verdict.checks_passed} passed, "
          f"{verdict.checks_failed} failed, {verdict.checks_warned} warned")
    print(f"Assessment  : {report.llm_assessment}")
    print(f"Recommend   : {report.recommendation}")
    print(f"Report path : {updated_state.validation_output.artifact_path}")
    return updated_state


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
    )
    if run_mode == "analysis":
        updated_state = run_analysis_stage(state, config)
        artifact = updated_state.analysis_output
        assert artifact is not None
        logger.info(
            "Application completed analysis-agent demo for issue_id=%s artifact_path=%s",
            artifact.summary.issue_id,
            artifact.artifact_path,
        )
        return

    if run_mode == "patch" and args.analysis_artifact:
        logger.info(
            "Application loading analysis artifact for patch run path=%s",
            args.analysis_artifact,
        )
        state = apply_analysis_artifact_to_state(state, args.analysis_artifact)

    if run_mode == "patch":
        updated_state = run_patch_stage(state, config)
        artifact = updated_state.patch_agent_output
        assert artifact is not None
        logger.info(
            "Application completed patch-agent demo for issue_id=%s artifact_path=%s patch_draft_path=%s",
            artifact.proposal.issue_id,
            artifact.artifact_path,
            artifact.patch_draft_path,
        )
        return

    if run_mode == "validation":
        updated_state = run_patch_stage(state, config)
        updated_state = run_validation_stage(updated_state, config)
        artifact = updated_state.validation_output
        assert artifact is not None
        logger.info(
            "Application completed validation-agent demo for issue_id=%s verdict=%s report_path=%s",
            artifact.report.issue_id,
            artifact.report.verdict.status,
            artifact.artifact_path,
        )
        return

    logger.info("Application starting connected full flow: analysis -> patch")
    updated_state = run_analysis_stage(state, config)
    analysis_artifact = updated_state.analysis_output
    assert analysis_artifact is not None
    logger.info(
        "Application completed analysis stage for full flow issue_id=%s artifact_path=%s",
        analysis_artifact.summary.issue_id,
        analysis_artifact.artifact_path,
    )

    updated_state = run_patch_stage(updated_state, config)
    patch_artifact = updated_state.patch_agent_output
    assert patch_artifact is not None
    logger.info(
        "Application completed full flow for issue_id=%s analysis_artifact=%s patch_artifact=%s",
        patch_artifact.proposal.issue_id,
        analysis_artifact.artifact_path,
        patch_artifact.artifact_path,
    )

    updated_state = run_validation_stage(updated_state, config)
    validation_artifact = updated_state.validation_output
    assert validation_artifact is not None
    logger.info(
        "Application completed validation stage for issue_id=%s verdict=%s report_path=%s",
        validation_artifact.report.issue_id,
        validation_artifact.report.verdict.status,
        validation_artifact.artifact_path,
    )


if __name__ == "__main__":
    main()
