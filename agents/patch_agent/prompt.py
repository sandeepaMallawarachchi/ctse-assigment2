"""Prompt templates for the Patch Generation Agent.

The final version will contain the system and task prompts used to guide
the local model toward focused, low-risk patch proposals.
"""

from orchestrator.state import PatchWorkflowState

PATCH_AGENT_SYSTEM_PROMPT = """
You are the Patch Generation Agent.
Produce minimal, explainable patch proposals using structured issue
context and repository findings only.
Avoid unrelated edits, keep the file scope narrow, explain rationale,
and prepare output for a downstream validation agent.
""".strip()

PATCH_AGENT_TASK_GUIDANCE = """
Inputs:
- structured issue context
- repository findings from the analysis stage

Output requirements:
- propose the smallest practical patch scope
- list intended files
- explain rationale and risk
- include checks for the Validation Agent
""".strip()


def build_patch_agent_user_prompt(state: PatchWorkflowState) -> str:
    """Render shared workflow state into a model-ready patch request.

    Args:
        state: Shared workflow state containing triage and analysis outputs.

    Returns:
        Prompt text asking the model to return a structured patch proposal.
    """

    findings_text = "\n".join(
        [
            (
                f"{index}. file={finding.file_path}; "
                f"reason={finding.reason}; "
                f"snippet={finding.snippet!r}"
            )
            for index, finding in enumerate(state.repository_findings, start=1)
        ]
    )
    if not findings_text:
        findings_text = "No repository findings were provided."

    expected_behavior = state.issue.expected_behavior or "Not provided."
    return f"""
Issue ID: {state.issue.issue_id}
Issue Title: {state.issue.title}
Issue Description: {state.issue.description}
Expected Behavior: {expected_behavior}

Repository Findings:
{findings_text}

Respond with a structured patch proposal that:
- stays limited to directly relevant files
- explains why each file is included
- estimates risk conservatively
- gives validation checks for the next agent
""".strip()
