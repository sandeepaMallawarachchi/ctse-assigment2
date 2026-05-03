"""Codebase Analysis Agent module.

This agent inspects a local repository, identifies relevant code locations,
and prepares structured findings for downstream patch generation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Protocol

"""This agent is designed to be flexible with or without a model-backed summary generator. 
   If no generator is provided, it will produce a deterministic summary based solely on the repository search results. 
   This allows for robust operation even in environments without access to language models, while still enabling enhanced summaries when a generator is available.
"""

from agents.analysis_agent.prompt import (
    ANALYSIS_AGENT_SYSTEM_PROMPT,
    build_analysis_user_prompt,
)

"""Data schemas for the analysis agent, including the structure of findings and summaries that are produced from repository analysis."""
from agents.analysis_agent.schema import AnalysisArtifact, AnalysisFinding, AnalysisSummary

"""Core state definitions for the patch workflow, including the structure of repository findings that are populated by this agent."""
from orchestrator.state import PatchWorkflowState, RepositoryFinding
from tools.analysis_tools.code_search import (
    CodeSearchResult,
    derive_search_terms,
    search_repository,
)

logger = logging.getLogger(__name__)

"""This module defines the CodebaseAnalysisAgent, which inspects a local repository to identify relevant code locations based on issue details. 
   It can optionally use a model-backed AnalysisSummaryGenerator to create structured summaries of the findings, but will gracefully fall back to a deterministic summary if no generator is provided or if the generator fails.
"""

class AnalysisSummaryGenerator(Protocol):
    """Protocol for optional model-backed analysis summarization."""

    def generate(
        self,
        state: PatchWorkflowState,
        search_terms: list[str],
        findings: list[CodeSearchResult],
    ) -> AnalysisSummary:
        """Create a structured analysis summary from search results."""

"""This is a concrete implementation of the AnalysisSummaryGenerator protocol that uses a local Ollama model via LangChain to generate analysis summaries.
   It expects the model to return output that can be coerced into the AnalysisSummary schema, and includes validation to ensure the model output meets quality standards before it is used downstream.
"""

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

"""The CodebaseAnalysisAgent is responsible for inspecting a local repository to identify relevant code locations based on issue details.
   It can optionally use a model-backed AnalysisSummaryGenerator to create structured summaries of the findings,
   but will gracefully fall back to a deterministic summary if no generator is provided or if the generator fails. 
   The agent performs a repository search using derived search terms from the issue details, generates an analysis summary, 
   validates the summary quality, and persists the findings and summary to disk for downstream use.
"""

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
        if state.triage_output is not None and state.triage_output.summary.search_keywords:
            search_terms = state.triage_output.summary.search_keywords
        else:
            search_terms = derive_search_terms(
                title=state.issue.title,
                description=state.issue.description,
                expected_behavior=state.issue.expected_behavior,
            )
        search_results = search_repository(
            repo_root=state.repository_root,
            search_terms=search_terms,
            target_file=state.target_code_file,
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
            self._validate_summary_quality(state, summary, findings)
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

    def _validate_summary_quality(
        self,
        state: PatchWorkflowState,
        summary: AnalysisSummary,
        findings: list[CodeSearchResult],
    ) -> None:
        """Reject incomplete model output before it reaches downstream agents."""

        if not summary.findings:
            raise ValueError("Model output must include at least one repository finding.")

        if not summary.summary.strip():
            raise ValueError("Model output must include a non-empty analysis summary.")

        allowed_files = {result.finding.file_path for result in findings}
        if allowed_files:
            invalid_files = [
                finding.file_path for finding in summary.findings
                if finding.file_path not in allowed_files
            ]
            if invalid_files:
                raise ValueError(
                    "Model output referenced files not produced by repository search: "
                    + ", ".join(invalid_files)
                )

        if state.target_code_file and len(summary.findings) > 1:
            raise ValueError(
                "Single-file analysis must not return findings for multiple files."
            )

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
