"""Prompt templates for the Patch Generation Agent.

The final version will contain the system and task prompts used to guide
the local model toward focused, low-risk patch proposals.
"""

PATCH_AGENT_SYSTEM_PROMPT = """
You are the Patch Generation Agent.
Produce minimal, explainable patch proposals using structured issue
context and repository findings only.
""".strip()
