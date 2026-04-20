"""Prompt templates for the Codebase Analysis Agent."""

from orchestrator.state import PatchWorkflowState

ANALYSIS_AGENT_SYSTEM_PROMPT = """
You are the Codebase Analysis Agent.
Inspect a local repository, identify the most relevant files and snippets,
and produce focused findings for downstream patch generation.
Avoid triage, patch writing, or validation decisions.
""".strip()

ANALYSIS_AGENT_TASK_GUIDANCE = """
Inputs:
- structured issue context
- local repository path

Output requirements:
- identify only the most relevant files
- include concise snippets and reasons
- keep findings minimal and actionable for the patch agent
""".strip()


def build_analysis_user_prompt(state: PatchWorkflowState, search_terms: list[str]) -> str:
    """Render analysis-stage context into a model-ready prompt."""

    expected_behavior = state.issue.expected_behavior or "Not provided."
    keyword_text = ", ".join(search_terms) or "No keywords derived."

    return f"""
Issue ID: {state.issue.issue_id}
Issue Title: {state.issue.title}
Issue Description: {state.issue.description}
Expected Behavior: {expected_behavior}
Repository Root: {state.repository_root}
Search Terms: {keyword_text}

Return a concise analysis summary with only the repository findings most relevant
to the reported issue. The findings should help a downstream patch agent choose
where to modify code.
""".strip()
