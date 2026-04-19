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


def summarize_change_scope(finding: RepositoryFinding) -> str:
    """Create a short human-readable summary for a file-level change.

    Args:
        finding: Repository analysis result associated with a candidate file.

    Returns:
        One-sentence summary describing why the file should be revisited.
    """

    return f"Review logic related to: {finding.reason.rstrip('.')}"


def estimate_risk_level(target_files: list[str]) -> str:
    """Estimate change risk from the number of touched files.

    Args:
        target_files: Ordered list of candidate files for the patch proposal.

    Returns:
        A qualitative risk label suitable for the patch schema.
    """

    file_count = len(target_files)
    if file_count <= 1:
        return "low"
    if file_count <= 3:
        return "medium"
    return "high"


def build_validation_focus(findings: list[RepositoryFinding]) -> list[str]:
    """Produce lightweight validation guidance for downstream review.

    Args:
        findings: Repository findings that informed the patch proposal.

    Returns:
        Ordered list of suggested validation checks.
    """

    checks: list[str] = ["Verify the reported issue path is resolved."]

    for finding in findings[:2]:
        checks.append(f"Re-test behavior around {finding.file_path}.")

    return checks
