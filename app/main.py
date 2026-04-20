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

from agents.patch_agent.agent import (
    OllamaPatchProposalGenerator,
    PatchGenerationAgent,
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
    """Parse command-line arguments for the patch-agent demo."""

    parser = argparse.ArgumentParser(description="Run the Patch Generation Agent demo.")
    parser.add_argument(
        "--agent",
        default="patch",
        choices=["patch"],
        help="Agent entrypoint to run. Additional agents will be added later.",
    )
    parser.add_argument(
        "--issue-file",
        default="data/issues/sample_issue.json",
        help="Path to a JSON issue payload file.",
    )
    return parser.parse_args()


def build_demo_state(
    issue_file: str,
) -> PatchWorkflowState:
    """Load a sample issue and create mock analysis findings for the patch demo."""

    sample_issue_path = Path(issue_file)
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


def main() -> None:
    """Run the patch-agent demo from the project root."""

    args = parse_args()
    config = AppConfig()
    configure_logging(config)
    logger = logging.getLogger(__name__)
    logger.info(
        "Application startup for Patch Generation Agent demo agent=%s",
        args.agent,
    )
    state = build_demo_state(
        issue_file=args.issue_file,
    )
    agent = build_patch_agent(config)
    updated_state = agent.run(state)

    artifact = updated_state.patch_agent_output
    assert artifact is not None
    logger.info(
        "Application completed patch-agent demo for issue_id=%s artifact_path=%s patch_draft_path=%s",
        artifact.proposal.issue_id,
        artifact.artifact_path,
        artifact.patch_draft_path,
    )

    print("Patch Generation Agent demo completed")
    print(f"Issue ID: {artifact.proposal.issue_id}")
    print(f"Target files: {', '.join(artifact.proposal.target_files)}")
    print(f"Risk level: {artifact.proposal.risk_level}")
    print(f"Artifact path: {artifact.artifact_path}")
    print(f"Patch draft path: {artifact.patch_draft_path}")


if __name__ == "__main__":
    main()
