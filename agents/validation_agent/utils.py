"""Utility helpers for the Validation & Report Agent.

Contains deterministic structural checks that evaluate a patch proposal
without requiring an LLM, and a fallback verdict builder used when the
Ollama model is unavailable.
"""

from agents.patch_agent.schema import PatchProposal
from agents.validation_agent.schema import (
    ConfidenceLevel,
    ValidationCheck,
    ValidationVerdict,
    VerdictStatus,
)

_RISK_FILE_THRESHOLDS: dict[str, range] = {
    "low": range(0, 2),       # 0–1 files
    "medium": range(2, 4),    # 2–3 files
    "high": range(4, 9999),   # 4+ files
}


def check_schema_completeness(proposal: PatchProposal) -> ValidationCheck:
    """Verify that required narrative fields on the proposal are non-empty.

    Args:
        proposal: Patch proposal to inspect.

    Returns:
        ValidationCheck with status 'pass' if summary and rationale are
        both non-empty, 'fail' otherwise.
    """

    missing = [
        field
        for field, value in [("summary", proposal.summary), ("rationale", proposal.rationale)]
        if not value or not value.strip()
    ]

    if missing:
        return ValidationCheck(
            name="schema_completeness",
            status="fail",
            detail=f"Required field(s) are empty: {', '.join(missing)}.",
        )
    return ValidationCheck(
        name="schema_completeness",
        status="pass",
        detail="All required narrative fields are present and non-empty.",
    )


def check_risk_file_consistency(proposal: PatchProposal) -> ValidationCheck:
    """Verify that the declared risk level is consistent with the file count.

    Expected thresholds: low=0–1 files, medium=2–3 files, high=4+ files.

    Args:
        proposal: Patch proposal to inspect.

    Returns:
        ValidationCheck with status 'pass' if consistent, 'warning' if the
        risk level appears underestimated for the number of target files.
    """

    file_count = len(proposal.target_files)
    expected_range = _RISK_FILE_THRESHOLDS.get(proposal.risk_level)

    if expected_range is None or file_count not in expected_range:
        return ValidationCheck(
            name="risk_file_consistency",
            status="warning",
            detail=(
                f"Declared risk '{proposal.risk_level}' may not reflect "
                f"{file_count} target file(s). Review risk estimate."
            ),
        )
    return ValidationCheck(
        name="risk_file_consistency",
        status="pass",
        detail=(
            f"Risk level '{proposal.risk_level}' is consistent with "
            f"{file_count} target file(s)."
        ),
    )


def check_change_plan_coverage(proposal: PatchProposal) -> ValidationCheck:
    """Verify that every target file has a corresponding change plan entry.

    Args:
        proposal: Patch proposal to inspect.

    Returns:
        ValidationCheck with status 'pass' if all target files are covered,
        'fail' listing the uncovered files otherwise.
    """

    planned_files = {entry.file_path for entry in proposal.change_plan}
    uncovered = [f for f in proposal.target_files if f not in planned_files]

    if uncovered:
        return ValidationCheck(
            name="change_plan_coverage",
            status="fail",
            detail=(
                f"Target file(s) missing a change plan entry: "
                f"{', '.join(uncovered)}."
            ),
        )
    return ValidationCheck(
        name="change_plan_coverage",
        status="pass",
        detail="Every target file has a corresponding change plan entry.",
    )


def check_validation_focus_populated(proposal: PatchProposal) -> ValidationCheck:
    """Verify that the patch agent supplied at least one validation focus item.

    Args:
        proposal: Patch proposal to inspect.

    Returns:
        ValidationCheck with status 'pass' if at least one focus item is
        present, 'warning' if the list is empty.
    """

    if not proposal.validation_focus:
        return ValidationCheck(
            name="validation_focus_populated",
            status="warning",
            detail="No validation focus items were provided by the Patch Agent.",
        )
    return ValidationCheck(
        name="validation_focus_populated",
        status="pass",
        detail=(
            f"{len(proposal.validation_focus)} validation focus item(s) "
            "provided for targeted review."
        ),
    )


def check_risk_notes_present(proposal: PatchProposal) -> ValidationCheck:
    """Verify that the patch agent documented at least one risk note.

    Args:
        proposal: Patch proposal to inspect.

    Returns:
        ValidationCheck with status 'pass' if risk notes exist,
        'warning' otherwise.
    """

    if not proposal.risk_notes:
        return ValidationCheck(
            name="risk_notes_present",
            status="warning",
            detail="No risk notes were provided. Risk reasoning is undocumented.",
        )
    return ValidationCheck(
        name="risk_notes_present",
        status="pass",
        detail=f"{len(proposal.risk_notes)} risk note(s) documented.",
    )


def run_structural_checks(proposal: PatchProposal) -> list[ValidationCheck]:
    """Run all deterministic structural checks against a patch proposal.

    Executes five rule-based checks in a fixed order. These checks do not
    require an LLM and always produce a deterministic result.

    Args:
        proposal: Patch proposal produced by the Patch Generation Agent.

    Returns:
        Ordered list of ValidationCheck results, one per check.
    """

    return [
        check_schema_completeness(proposal),
        check_risk_file_consistency(proposal),
        check_change_plan_coverage(proposal),
        check_validation_focus_populated(proposal),
        check_risk_notes_present(proposal),
    ]


def compute_verdict(
    checks: list[ValidationCheck],
    risk_level: str,
) -> ValidationVerdict:
    """Derive a deterministic ValidationVerdict from structural check results.

    Used as the fallback when the Ollama model is unavailable. The status
    is determined by the presence of failures; confidence is shaped by the
    declared risk level of the patch.

    Args:
        checks: Results from run_structural_checks().
        risk_level: Risk level declared in the patch proposal ("low",
            "medium", or "high").

    Returns:
        ValidationVerdict summarising the check outcomes and overall decision.
    """

    passed = sum(1 for c in checks if c.status == "pass")
    failed = sum(1 for c in checks if c.status == "fail")
    warned = sum(1 for c in checks if c.status == "warning")

    status: VerdictStatus
    confidence: ConfidenceLevel

    if failed > 0:
        status = "rejected" if failed >= 2 else "needs_review"
        confidence = "high" if failed >= 2 else "medium"
        rationale = (
            f"{failed} structural check(s) failed. "
            "The proposal requires revision before it can be approved."
        )
    elif warned > 0:
        status = "needs_review"
        confidence = "medium" if risk_level == "high" else "high"
        rationale = (
            f"All checks passed but {warned} warning(s) require attention "
            "before the patch can be confidently approved."
        )
    else:
        status = "approved"
        confidence = "low" if risk_level == "high" else "high"
        rationale = (
            "All structural checks passed with no warnings. "
            f"Risk level is '{risk_level}'."
        )

    return ValidationVerdict(
        status=status,
        confidence=confidence,
        rationale=rationale,
        checks_passed=passed,
        checks_failed=failed,
        checks_warned=warned,
    )
