"""Custom issue parsing helpers for the Triage Agent."""

from __future__ import annotations

import re

from agents.triage_agent.schema import IssueType, PriorityLevel, TriageSummary
from orchestrator.state import IssueContext


def _extract_keywords(*parts: str) -> list[str]:
    """Extract ordered, de-duplicated issue keywords from text."""

    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "after",
        "should",
        "does",
        "not",
        "that",
        "this",
        "when",
        "from",
        "into",
    }
    joined = " ".join(part for part in parts if part)
    words = re.findall(r"[A-Za-z_]{3,}", joined.lower())
    keywords: list[str] = []
    seen: set[str] = set()

    for word in words:
        if word in stop_words or word in seen:
            continue
        seen.add(word)
        keywords.append(word)
    return keywords[:8]


def classify_issue_type(title: str, description: str) -> IssueType:
    """Classify an issue using lightweight keyword heuristics."""

    lowered = f"{title} {description}".lower()
    if any(term in lowered for term in ["fix", "bug", "error", "fail", "crash", "stuck"]):
        return "bug"
    if any(term in lowered for term in ["feature", "add", "support", "allow"]):
        return "feature"
    if any(term in lowered for term in ["refactor", "cleanup", "simplify"]):
        return "refactor"
    return "unknown"


def estimate_priority(title: str, description: str) -> PriorityLevel:
    """Estimate issue priority using simple severity heuristics."""

    lowered = f"{title} {description}".lower()
    if any(term in lowered for term in ["crash", "security", "data loss", "blocked"]):
        return "high"
    if any(term in lowered for term in ["fail", "error", "broken", "stuck"]):
        return "medium"
    return "low"


def parse_issue(issue: IssueContext) -> TriageSummary:
    """Parse a structured issue into a downstream-ready triage summary.

    Args:
        issue: Shared issue context supplied to the Triage Agent.

    Returns:
        Structured triage summary for later stages.
    """

    issue_type = classify_issue_type(issue.title, issue.description)
    priority = estimate_priority(issue.title, issue.description)
    keywords = _extract_keywords(
        issue.title,
        issue.description,
        issue.expected_behavior or "",
    )
    expected_behavior = issue.expected_behavior.strip() if issue.expected_behavior else None

    return TriageSummary(
        issue_id=issue.issue_id,
        issue_type=issue_type,
        priority=priority,
        normalized_title=issue.title.strip(),
        normalized_description=issue.description.strip(),
        expected_behavior=expected_behavior,
        search_keywords=keywords,
        summary=(
            f"Classified as a {issue_type} issue with {priority} priority. "
            "Prepared normalized issue details and search keywords for downstream agents."
        ),
    )
