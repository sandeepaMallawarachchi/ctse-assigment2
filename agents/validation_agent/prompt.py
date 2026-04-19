"""Prompt templates for the Validation & Report Agent.

Contains the system prompt that defines the agent's persona and constraints,
and a user prompt builder that renders shared workflow state into a model-ready
validation request.
"""

from agents.validation_agent.schema import ValidationCheck
from orchestrator.state import PatchWorkflowState

VALIDATION_AGENT_SYSTEM_PROMPT = """
You are the Validation Agent in an autonomous software issue resolution system.
Your role is to critically review a proposed code patch and decide whether it
is safe, targeted, and likely to resolve the reported issue.

Constraints:
- Be conservative. Prefer "needs_review" over "approved" when uncertain.
- Never invent file contents, code, or facts not present in the input.
- Base your verdict only on the provided proposal metadata and check results.
- Your verdict status must be exactly one of: approved, rejected, needs_review.
- Your confidence must be exactly one of: high, medium, low.
- Keep llm_assessment under 80 words and focus on the most important concern.
- Keep recommendation to a single, actionable sentence for the engineering team.
""".strip()

VALIDATION_AGENT_TASK_GUIDANCE = """
Inputs:
- issue context (id, title, description, expected behavior)
- patch proposal metadata (summary, target files, risk level, rationale)
- results of deterministic structural checks already run on the proposal

Output requirements:
- verdict: status + confidence + rationale + check counts
- llm_assessment: short narrative on proposal quality and key concerns
- recommendation: one clear sentence for the engineering team
""".strip()


def _format_checks(checks: list[ValidationCheck]) -> str:
    """Render structural check results as a numbered list for the prompt.

    Args:
        checks: Ordered list of completed structural check results.

    Returns:
        Formatted multi-line string, one check per line.
    """

    if not checks:
        return "No structural checks were run."

    return "\n".join(
        f"{i}. [{check.status.upper()}] {check.name}: {check.detail}"
        for i, check in enumerate(checks, start=1)
    )


def build_validation_user_prompt(
    state: PatchWorkflowState,
    checks: list[ValidationCheck],
) -> str:
    """Render shared workflow state and check results into a model-ready prompt.

    Includes issue context, patch proposal metadata, and the results of all
    deterministic structural checks. The LLM is asked to produce a verdict,
    a short assessment, and a single recommendation sentence.

    Args:
        state: Shared workflow state containing issue context and the patch
            proposal produced by the Patch Generation Agent.
        checks: Completed structural check results from run_structural_checks().

    Returns:
        Prompt text asking the model to return a structured validation verdict.
    """

    assert state.patch_agent_output is not None, (
        "build_validation_user_prompt requires patch_agent_output to be set on state."
    )

    proposal = state.patch_agent_output.proposal
    expected_behavior = state.issue.expected_behavior or "Not specified."

    passed = sum(1 for c in checks if c.status == "pass")
    failed = sum(1 for c in checks if c.status == "fail")
    warned = sum(1 for c in checks if c.status == "warning")

    target_files_text = (
        "\n".join(f"  - {f}" for f in proposal.target_files)
        if proposal.target_files
        else "  (none listed)"
    )

    validation_focus_text = (
        "\n".join(f"  - {item}" for item in proposal.validation_focus)
        if proposal.validation_focus
        else "  (none provided)"
    )

    checks_text = _format_checks(checks)

    return f"""
Issue ID: {state.issue.issue_id}
Issue Title: {state.issue.title}
Issue Description: {state.issue.description}
Expected Behavior: {expected_behavior}

--- Patch Proposal ---
Summary: {proposal.summary}
Risk Level: {proposal.risk_level}
Rationale: {proposal.rationale}

Target Files:
{target_files_text}

Validation Focus from Patch Agent:
{validation_focus_text}

--- Structural Check Results ({passed} passed, {failed} failed, {warned} warned) ---
{checks_text}

Based on the above, respond with:
- verdict: status (approved/rejected/needs_review), confidence (high/medium/low),
  rationale, and the check counts ({passed} passed, {failed} failed, {warned} warned)
- llm_assessment: short narrative under 80 words on the proposal quality
- recommendation: one actionable sentence for the engineering team
""".strip()
