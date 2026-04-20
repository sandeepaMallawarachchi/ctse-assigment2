"""Custom repository search helpers for the Codebase Analysis Agent."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from orchestrator.state import RepositoryFinding


class CodeSearchResult:
    """Container for a repository finding plus its internal relevance score."""

    def __init__(self, finding: RepositoryFinding, score: int) -> None:
        self.finding = finding
        self.score = score


def derive_search_terms(
    title: str,
    description: str,
    expected_behavior: Optional[str] = None,
) -> list[str]:
    """Extract simple issue keywords for repository inspection.

    Args:
        title: Short issue title.
        description: Expanded issue description.
        expected_behavior: Optional desired behavior text.

    Returns:
        Ordered list of normalized search terms with duplicates removed.
    """

    raw_text = " ".join(part for part in [title, description, expected_behavior or ""] if part)
    words = re.findall(r"[A-Za-z_]{3,}", raw_text.lower())
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

    terms: list[str] = []
    seen: set[str] = set()
    for word in words:
        if word in stop_words or word in seen:
            continue
        seen.add(word)
        terms.append(word)
    return terms[:8]


def _iter_candidate_files(repo_root: Path) -> list[Path]:
    """Return text-like repository files to inspect."""

    allowed_suffixes = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md"}
    disallowed_parts = {".git", ".venv", "__pycache__", "node_modules"}

    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in disallowed_parts for part in path.parts):
            continue
        if path.suffix.lower() in allowed_suffixes:
            files.append(path)
    return files


def _score_file_content(content: str, search_terms: list[str]) -> int:
    """Score a file by simple keyword frequency."""

    lowered = content.lower()
    return sum(lowered.count(term.lower()) for term in search_terms)


def _line_match_score(line: str, search_terms: list[str]) -> int:
    """Score a single line by keyword matches and code-like signals."""

    lowered = line.lower()
    score = sum(lowered.count(term.lower()) for term in search_terms)
    stripped = line.strip()
    if not stripped:
        return 0

    if stripped.startswith(("def ", "if ", "return ", "class ", "for ", "while ")):
        score += 2
    if "=" in stripped and not stripped.startswith("#"):
        score += 1
    if stripped.startswith(("\"\"\"", "#")):
        score -= 2
    return score


def _extract_best_snippet(
    content: str,
    search_terms: list[str],
) -> tuple[str, Optional[int], Optional[int]]:
    """Extract a small snippet centered on the strongest matching code line."""

    lines = content.splitlines()
    best_index: Optional[int] = None
    best_score = 0

    for index, line in enumerate(lines):
        score = _line_match_score(line, search_terms)
        if score > best_score:
            best_score = score
            best_index = index

    if best_index is not None and best_score > 0:
        start = max(0, best_index - 1)
        end = min(len(lines), best_index + 2)
        snippet = "\n".join(lines[start:end]).strip()
        return snippet, start + 1, end

    snippet = "\n".join(lines[:3]).strip()
    return snippet, 1 if lines else None, min(len(lines), 3) if lines else None


def search_repository(
    repo_root: str,
    search_terms: list[str],
    max_results: int = 3,
) -> list[CodeSearchResult]:
    """Search a local repository for issue-relevant files and snippets.

    Args:
        repo_root: Local repository path to inspect.
        search_terms: Keywords derived from the issue context.
        max_results: Maximum number of results to return.

    Returns:
        Ordered list of relevant search results.

    Raises:
        FileNotFoundError: If the repository root does not exist.
        ValueError: If the repository root is not a directory.
    """

    repo_path = Path(repo_root)
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo_root}")
    if not repo_path.is_dir():
        raise ValueError(f"Repository path must be a directory: {repo_root}")

    results: list[CodeSearchResult] = []
    for file_path in _iter_candidate_files(repo_path):
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        score = _score_file_content(content, search_terms)
        if score <= 0:
            continue

        snippet, line_start, line_end = _extract_best_snippet(content, search_terms)
        relative_path = file_path.relative_to(repo_path).as_posix()
        reason = (
            f"Matched issue keywords {', '.join(search_terms[:3])} in {relative_path}."
            if search_terms
            else f"Matched issue context in {relative_path}."
        )
        results.append(
            CodeSearchResult(
                finding=RepositoryFinding(
                    file_path=relative_path,
                    snippet=snippet,
                    reason=reason,
                    line_start=line_start,
                    line_end=line_end,
                ),
                score=score,
            )
        )

    results.sort(key=lambda item: item.score, reverse=True)
    return results[:max_results]
