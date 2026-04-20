"""Codebase Analysis Agent module.

This agent inspects a local repository, identifies relevant code locations,
and prepares structured findings for downstream patch generation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Protocol

from agents.analysis_agent.prompt import (
    ANALYSIS_AGENT_SYSTEM_PROMPT,
    build_analysis_user_prompt,
)
from agents.analysis_agent.schema import AnalysisArtifact, AnalysisFinding, AnalysisSummary
from orchestrator.state import PatchWorkflowState, RepositoryFinding
from tools.analysis_tools.code_search import (
    CodeSearchResult,
    derive_search_terms,
    search_repository,
)

logger = logging.getLogger(__name__)


class AnalysisSummaryGenerator(Protocol):
    """Protocol for optional model-backed analysis summarization."""

    def generate(
        self,
        state: PatchWorkflowState,
        search_terms: list[str],
        findings: list[CodeSearchResult],
    ) -> AnalysisSummary:
        """Create a structured analysis summary from search results."""


class OllamaAnalysisSummaryGenerator:
    """Generate analysis summaries with Ollama via LangChain."""

    def __init__(self, model_name: str, base_url: str) -> None:
        self.model_name = model_name
        self.base_url = base_url

    def generate(
        self,
        state: PatchWorkflowState,
        search_terms: list[str],
        findings: list[CodeSearchResult],
    ) -> AnalysisSummary:
        """Call the local Ollama model and coerce output into AnalysisSummary."""

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
        ).with_structured_output(AnalysisSummary)

        return llm.invoke(
            [
                ("system", ANALYSIS_AGENT_SYSTEM_PROMPT),
                ("human", build_analysis_user_prompt(state, search_terms)),
            ]
        )


class CodebaseAnalysisAgent:
    """Specialized agent that finds relevant files and snippets in a repo."""

    def __init__(
        self,
        output_dir: str = "outputs/reports",
        summary_generator: Optional[AnalysisSummaryGenerator] = None,
        allow_fallback: bool = True,
    ) -> None:
        self.output_dir = output_dir
        self.summary_generator = summary_generator
        self.allow_fallback = allow_fallback

    def run(self, state: PatchWorkflowState) -> PatchWorkflowState:
        """Inspect the configured repository and populate repository findings."""

        logger.info(
            "CodebaseAnalysisAgent started for issue_id=%s repo_root=%s",
            state.issue.issue_id,
            state.repository_root,
        )
        search_terms = derive_search_terms(
            title=state.issue.title,
            description=state.issue.description,
            expected_behavior=state.issue.expected_behavior,
        )
        search_results = search_repository(
            repo_root=state.repository_root,
            search_terms=search_terms,
        )
        summary = self._generate_summary(state, search_terms, search_results)
        state.repository_findings = [
            RepositoryFinding(
                file_path=finding.file_path,
                snippet=finding.snippet,
                reason=finding.reason,
                line_start=finding.line_start,
                line_end=finding.line_end,
            )
            for finding in summary.findings
        ]
        state.analysis_output = self._write_analysis_artifact(summary)
        logger.info(
            "CodebaseAnalysisAgent completed for issue_id=%s findings=%d artifact_path=%s",
            state.issue.issue_id,
            len(summary.findings),
            state.analysis_output.artifact_path,
        )
        return state

    def _generate_summary(
        self,
        state: PatchWorkflowState,
        search_terms: list[str],
        findings: list[CodeSearchResult],
    ) -> AnalysisSummary:
        """Use the configured generator and fall back when appropriate."""

        if self.summary_generator is None:
            logger.info(
                "CodebaseAnalysisAgent using deterministic analysis summary for issue_id=%s",
                state.issue.issue_id,
            )
            return self._build_fallback_summary(state, search_terms, findings)

        try:
            logger.info(
                "CodebaseAnalysisAgent requesting model-backed summary for issue_id=%s",
                state.issue.issue_id,
            )
            summary = self.summary_generator.generate(state, search_terms, findings)
            self._validate_summary_quality(summary)
            logger.info(
                "CodebaseAnalysisAgent accepted model-backed summary for issue_id=%s",
                state.issue.issue_id,
            )
            return summary
        except Exception as exc:
            if not self.allow_fallback:
                logger.exception(
                    "CodebaseAnalysisAgent failed without fallback for issue_id=%s",
                    state.issue.issue_id,
                )
                raise
            logger.warning(
                "CodebaseAnalysisAgent falling back for issue_id=%s reason=%s",
                state.issue.issue_id,
                exc,
            )
            return self._build_fallback_summary(state, search_terms, findings)

    def _build_fallback_summary(
        self,
        state: PatchWorkflowState,
        search_terms: list[str],
        findings: list[CodeSearchResult],
    ) -> AnalysisSummary:
        """Create a deterministic analysis summary from tool output."""

        summary_text = (
            "Identified candidate files by matching issue keywords against the local "
            "repository and extracting the most relevant snippets."
        )
        return AnalysisSummary(
            issue_id=state.issue.issue_id,
            repo_path=state.repository_root,
            search_terms=search_terms,
            findings=[
                AnalysisFinding(
                    file_path=result.finding.file_path,
                    snippet=result.finding.snippet,
                    reason=result.finding.reason,
                    line_start=result.finding.line_start,
                    line_end=result.finding.line_end,
                )
                for result in findings
            ],
            summary=summary_text,
        )

    def _validate_summary_quality(self, summary: AnalysisSummary) -> None:
        """Reject incomplete model output before it reaches downstream agents."""

        if not summary.findings:
            raise ValueError("Model output must include at least one repository finding.")

        if not summary.summary.strip():
            raise ValueError("Model output must include a non-empty analysis summary.")

    def _write_analysis_artifact(self, summary: AnalysisSummary) -> AnalysisArtifact:
        """Persist the analysis summary to disk for inspection."""

        output_path = Path(self.output_dir) / f"{summary.issue_id}_analysis.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            summary.model_dump(mode="json")
            if hasattr(summary, "model_dump")
            else summary.dict()
        )
        with output_path.open("w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, indent=2)

        return AnalysisArtifact(summary=summary, artifact_path=str(output_path))
