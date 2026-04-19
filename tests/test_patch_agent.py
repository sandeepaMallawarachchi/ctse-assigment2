"""Starter tests for the Patch Generation Agent."""

from agents.patch_agent.utils import collect_candidate_files
from orchestrator.state import RepositoryFinding


def test_collect_candidate_files_returns_unique_paths() -> None:
    """The helper should preserve order while removing duplicates."""

    findings = [
        RepositoryFinding(file_path="app/auth.py", snippet="a", reason="auth flow"),
        RepositoryFinding(file_path="app/auth.py", snippet="b", reason="retry logic"),
        RepositoryFinding(file_path="app/ui.py", snippet="c", reason="button state"),
    ]

    assert collect_candidate_files(findings) == ["app/auth.py", "app/ui.py"]
