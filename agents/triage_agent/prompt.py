"""Prompt templates for the Triage Agent."""

from orchestrator.state import PatchWorkflowState

TRIAGE_AGENT_SYSTEM_PROMPT = """
You are the Triage Agent.
Read an issue report, classify it, normalize the problem statement,
estimate priority, and extract repository-search keywords for downstream agents.
Do not inspect code, write patches, or validate fixes.
""".strip()

TRIAGE_AGENT_TASK_GUIDANCE = """
Inputs:
- structured issue payload

Output requirements:
- classify issue type
- estimate priority
- normalize title and description
- extract concise search keywords
- keep the output focused for analysis and patch generation
""".strip()


def build_triage_user_prompt(state: PatchWorkflowState) -> str:
    """Render issue context into a model-ready triage request."""

    expected_behavior = state.issue.expected_behavior or "Not provided."
    return f"""
Issue ID: {state.issue.issue_id}
Issue Title: {state.issue.title}
Issue Description: {state.issue.description}
Expected Behavior: {expected_behavior}

Produce a structured triage summary that will help downstream agents inspect
the codebase and generate a focused patch proposal.
""".strip()
