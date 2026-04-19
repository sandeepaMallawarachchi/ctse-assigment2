"""Utility helpers for the Patch Generation Agent.

Helper functions added here should stay narrowly focused on patch
preparation and avoid overlapping with orchestration or validation.
"""

from orchestrator.state import RepositoryFinding


def collect_candidate_files(findings: list[RepositoryFinding]) -> list[str]:
    """Extract unique candidate file paths from repository findings."""

    seen: set[str] = set()
    ordered_paths: list[str] = []

    for finding in findings:
        if finding.file_path not in seen:
            seen.add(finding.file_path)
            ordered_paths.append(finding.file_path)

    return ordered_paths
