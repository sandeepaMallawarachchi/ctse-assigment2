"""Triage Agent module.

This agent reads an issue report, structures it for downstream use, and
prepares triage metadata for the analysis and patch stages.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Protocol

from agents.triage_agent.prompt import (
    TRIAGE_AGENT_SYSTEM_PROMPT,
    build_triage_user_prompt,
)
from agents.triage_agent.schema import TriageArtifact, TriageSummary
from orchestrator.state import PatchWorkflowState
from tools.triage_tools.issue_parser import parse_issue

logger = logging.getLogger(__name__)


class TriageSummaryGenerator(Protocol):
    """Protocol for optional model-backed triage summarization."""

    def generate(self, state: PatchWorkflowState) -> TriageSummary:
        """Create a structured triage summary from issue context."""


class OllamaTriageSummaryGenerator:
    """Generate triage summaries with Ollama via LangChain."""

    def __init__(self, model_name: str, base_url: str) -> None:
        self.model_name = model_name
        self.base_url = base_url

    def generate(self, state: PatchWorkflowState) -> TriageSummary:
        """Call the local Ollama model and coerce output into TriageSummary."""

        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError(
                "langchain-ollama is not installed. Install requirements first."
            ) from exc

        llm = ChatOllama(
            model=self.model_name,
            base_url=self.base_url,
            temperature=0,
        ).with_structured_output(TriageSummary)

        return llm.invoke(
            [
                ("system", TRIAGE_AGENT_SYSTEM_PROMPT),
                ("human", build_triage_user_prompt(state)),
            ]
        )


class TriageAgent:
    """Specialized agent that prepares issue context for downstream agents."""

    def __init__(
        self,
        output_dir: str = "outputs/reports",
        summary_generator: Optional[TriageSummaryGenerator] = None,
        allow_fallback: bool = True,
    ) -> None:
        self.output_dir = output_dir
        self.summary_generator = summary_generator
        self.allow_fallback = allow_fallback

    def run(self, state: PatchWorkflowState) -> PatchWorkflowState:
        """Triage the issue and attach a structured triage artifact to state."""

        logger.info("TriageAgent started for issue_id=%s", state.issue.issue_id)
        summary = self._generate_summary(state)
        if not summary.expected_behavior and state.issue.expected_behavior:
            summary.expected_behavior = state.issue.expected_behavior.strip()
        state.issue.title = summary.normalized_title
        state.issue.description = summary.normalized_description
        state.issue.expected_behavior = summary.expected_behavior
        state.triage_output = self._write_triage_artifact(summary)
        logger.info(
            "TriageAgent completed for issue_id=%s issue_type=%s priority=%s artifact_path=%s",
            summary.issue_id,
            summary.issue_type,
            summary.priority,
            state.triage_output.artifact_path,
        )
        return state

    def _generate_summary(self, state: PatchWorkflowState) -> TriageSummary:
        """Use the configured generator and fall back when appropriate."""

        if self.summary_generator is None:
            logger.info(
                "TriageAgent using deterministic triage summary for issue_id=%s",
                state.issue.issue_id,
            )
            return parse_issue(state.issue)

        try:
            logger.info(
                "TriageAgent requesting model-backed summary for issue_id=%s",
                state.issue.issue_id,
            )
            summary = self.summary_generator.generate(state)
            self._validate_summary_quality(summary)
            logger.info(
                "TriageAgent accepted model-backed summary for issue_id=%s",
                state.issue.issue_id,
            )
            return summary
        except Exception as exc:
            if not self.allow_fallback:
                logger.exception(
                    "TriageAgent failed without fallback for issue_id=%s",
                    state.issue.issue_id,
                )
                raise
            logger.warning(
                "TriageAgent falling back for issue_id=%s reason=%s",
                state.issue.issue_id,
                exc,
            )
            return parse_issue(state.issue)

    def _validate_summary_quality(self, summary: TriageSummary) -> None:
        """Reject incomplete model output before it reaches downstream agents."""

        if not summary.normalized_title.strip():
            raise ValueError("Model output must include a normalized title.")
        if not summary.normalized_description.strip():
            raise ValueError("Model output must include a normalized description.")
        if not summary.search_keywords:
            raise ValueError("Model output must include search keywords.")

    def _write_triage_artifact(self, summary: TriageSummary) -> TriageArtifact:
        """Persist the triage summary to disk for inspection."""

        output_path = Path(self.output_dir) / f"{summary.issue_id}_triage.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            summary.model_dump(mode="json")
            if hasattr(summary, "model_dump")
            else summary.dict()
        )
        with output_path.open("w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, indent=2)

        return TriageArtifact(summary=summary, artifact_path=str(output_path))
