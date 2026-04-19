"""Custom tool for preparing patch proposal artifacts.

The full implementation will later convert model output into a stable,
serializable patch artifact that can be reviewed by the validation agent.
"""

from pathlib import Path


def build_patch_output_path(issue_id: str, output_dir: str = "outputs/patches") -> Path:
    """Create a deterministic output path for a proposed patch artifact.

    Args:
        issue_id: Unique issue identifier used in the output filename.
        output_dir: Directory where patch proposal files will be stored.

    Returns:
        Path pointing to the target patch artifact location.

    Raises:
        ValueError: If the issue identifier is empty or only whitespace.
    """

    normalized_issue_id = issue_id.strip()
    if not normalized_issue_id:
        raise ValueError("issue_id must be a non-empty string")

    return Path(output_dir) / f"{normalized_issue_id}_patch.json"
