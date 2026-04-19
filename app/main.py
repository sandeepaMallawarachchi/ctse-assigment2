"""Application entrypoint for running the local MAS prototype.

This file will later initialize configuration, shared state, and the
orchestrator entry flow. For now it provides a small patch-agent demo.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


def build_demo_state() -> PatchWorkflowState:
    """Load a sample issue and create mock analysis findings for the demo."""

    sample_issue_path = Path("data/issues/sample_issue.json")
    issue_payload = json.loads(sample_issue_path.read_text(encoding="utf-8"))

    return PatchWorkflowState(
        issue=IssueContext(**issue_payload),
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


def main() -> None:
    """Run the patch-agent demo from the project root."""

    config = AppConfig()
    state = build_demo_state()
    agent = build_patch_agent(config)
    updated_state = agent.run(state)

    artifact = updated_state.patch_agent_output
    assert artifact is not None

    print("Patch Generation Agent demo completed")
    print(f"Issue ID: {artifact.proposal.issue_id}")
    print(f"Target files: {', '.join(artifact.proposal.target_files)}")
    print(f"Risk level: {artifact.proposal.risk_level}")
    print(f"Artifact path: {artifact.artifact_path}")

    # --- Validation & Report Agent ---
    validation_agent = build_validation_agent(config)
    updated_state = validation_agent.run(updated_state)

    report = updated_state.validation_output.report
    verdict = report.verdict

    print("\nValidation & Report Agent completed")
    print(f"Verdict     : {verdict.status} (confidence: {verdict.confidence})")
    print(f"Checks      : {verdict.checks_passed} passed, "
          f"{verdict.checks_failed} failed, {verdict.checks_warned} warned")
    print(f"Assessment  : {report.llm_assessment}")
    print(f"Recommend   : {report.recommendation}")
    print(f"Report path : {updated_state.validation_output.artifact_path}")


if __name__ == "__main__":
    main()
