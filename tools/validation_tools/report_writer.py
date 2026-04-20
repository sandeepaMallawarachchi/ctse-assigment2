"""Custom tool for writing validation report artifacts to disk.

This tool serializes a completed FinalReport into a stable JSON file that
can be reviewed by downstream consumers or included in the final MAS output.
"""

import json
from pathlib import Path

from agents.validation_agent.schema import FinalReport, ValidationArtifact, ValidationVerdict


def _report_to_json_dict(report: FinalReport) -> dict[str, object]:
    """Convert a FinalReport Pydantic model to a JSON-safe dictionary.

    Supports both Pydantic v1 (.dict) and v2 (.model_dump) serialization.

    Args:
        report: Completed validation report to serialize.

    Returns:
        JSON-safe dictionary representation of the report.
    """

    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    return report.dict()


def build_report_output_path(issue_id: str, output_dir: str = "outputs/reports") -> Path:
    """Construct a deterministic output path for a validation report artifact.

    Args:
        issue_id: Unique issue identifier used to name the output file.
        output_dir: Directory where validation report files will be stored.

    Returns:
        Path object pointing to the target report artifact location.

    Raises:
        ValueError: If issue_id is empty or contains only whitespace.
    """

    normalized_id = issue_id.strip()
    if not normalized_id:
        raise ValueError("issue_id must be a non-empty string.")

    return Path(output_dir) / f"{normalized_id}_validation.json"


def write_validation_report(
    report: FinalReport,
    output_dir: str = "outputs/reports",
) -> ValidationArtifact:
    """Serialize a completed validation report to a JSON artifact on disk.

    Writes the full FinalReport (structural checks, LLM verdict, and
    recommendation) to a JSON file under the specified output directory.
    The directory is created automatically if it does not exist.

    Args:
        report: Completed validation report produced by the Validation Agent.
        output_dir: Directory where the serialized artifact will be written.
            Defaults to "outputs/reports".

    Returns:
        ValidationArtifact containing the original report and the path of
        the written file, suitable for downstream agents or human review.

    Raises:
        ValueError: If report.issue_id is empty or contains only whitespace.
        OSError: If the output directory cannot be created or the file
            cannot be written due to a filesystem permission error.
        TypeError: If the report cannot be serialized to JSON.

    Example:
        >>> report = FinalReport(
        ...     issue_id="ISSUE-007",
        ...     patch_summary="Fix null check in auth handler.",
        ...     target_files=["app/auth.py"],
        ...     risk_level="low",
        ...     checks=[],
        ...     verdict=ValidationVerdict(
        ...         status="approved", confidence="high",
        ...         rationale="All checks passed.",
        ...         checks_passed=5, checks_failed=0, checks_warned=0,
        ...     ),
        ...     llm_assessment="The proposal is narrow and well-justified.",
        ...     recommendation="Approve and proceed to merge.",
        ... )
        >>> artifact = write_validation_report(report)
        >>> artifact.artifact_path
        'outputs/reports/ISSUE-007_validation.json'
    """

    output_path = build_report_output_path(report.issue_id, output_dir=output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = _report_to_json_dict(report)
    with output_path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)

    return ValidationArtifact(report=report, artifact_path=str(output_path))
