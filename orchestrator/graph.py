"""LangGraph workflow for the local MAS orchestrator.

This module wires the specialized agents into a real stateful workflow so the
system can be evaluated as an orchestrated MAS rather than as a sequence of
manual function calls.
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import AppConfig
from orchestrator.state import PatchWorkflowState


class WorkflowStateDict(TypedDict, total=False):
    """Lightweight LangGraph state container mirroring PatchWorkflowState."""

    issue: Any
    run_id: str
    repository_root: str
    target_code_file: str
    repository_findings: list[Any]
    execution_trace: list[str]
    triage_output: Any
    analysis_output: Any
    patch_agent_output: Any
    validation_output: Any


def _state_to_dict(state: PatchWorkflowState) -> WorkflowStateDict:
    """Convert a Pydantic workflow state into a LangGraph-friendly dictionary."""

    return WorkflowStateDict(
        issue=state.issue,
        run_id=state.run_id,
        repository_root=state.repository_root,
        target_code_file=state.target_code_file,
        repository_findings=list(state.repository_findings),
        execution_trace=list(state.execution_trace),
        triage_output=state.triage_output,
        analysis_output=state.analysis_output,
        patch_agent_output=state.patch_agent_output,
        validation_output=state.validation_output,
    )


def _dict_to_state(payload: WorkflowStateDict) -> PatchWorkflowState:
    """Convert LangGraph state back into the shared Pydantic workflow model."""

    return PatchWorkflowState(**payload)


def _build_trace_update(state: PatchWorkflowState, stage_name: str) -> dict[str, Any]:
    """Append one stage name to the shared execution trace."""

    return {"execution_trace": state.execution_trace + [stage_name]}


def _make_stateful_node(
    stage_name: str,
    runner: Callable[[PatchWorkflowState], PatchWorkflowState],
) -> Callable[[WorkflowStateDict], WorkflowStateDict]:
    """Wrap an agent runner so it can be executed inside LangGraph."""

    def _node(payload: WorkflowStateDict) -> WorkflowStateDict:
        state = _dict_to_state(payload)
        updated_state = runner(state)
        update_payload = _state_to_dict(updated_state)
        update_payload.update(_build_trace_update(updated_state, stage_name))
        return update_payload

    return _node


def build_workflow(
    config: AppConfig,
    build_triage_agent: Callable[[AppConfig], Any],
    build_analysis_agent: Callable[[AppConfig], Any],
    build_patch_agent: Callable[[AppConfig], Any],
    build_validation_agent: Callable[[AppConfig], Any],
    run_mode: str = "full",
    analysis_ready: bool = False,
):
    """Build a LangGraph workflow for one of the supported run modes."""

    graph = StateGraph(WorkflowStateDict)

    triage_node = _make_stateful_node(
        "triage",
        lambda state: build_triage_agent(config).run(state),
    )
    analysis_node = _make_stateful_node(
        "analysis",
        lambda state: build_analysis_agent(config).run(state),
    )
    patch_node = _make_stateful_node(
        "patch",
        lambda state: build_patch_agent(config).run(state),
    )
    validation_node = _make_stateful_node(
        "validation",
        lambda state: build_validation_agent(config).run(state),
    )

    if run_mode == "triage":
        graph.add_node("triage", triage_node)
        graph.add_edge(START, "triage")
        graph.add_edge("triage", END)
        return graph.compile()

    if run_mode == "analysis":
        graph.add_node("analysis", analysis_node)
        graph.add_edge(START, "analysis")
        graph.add_edge("analysis", END)
        return graph.compile()

    if run_mode == "patch":
        graph.add_node("patch", patch_node)
        if analysis_ready:
            graph.add_edge(START, "patch")
        else:
            graph.add_node("analysis", analysis_node)
            graph.add_edge(START, "analysis")
            graph.add_edge("analysis", "patch")
        graph.add_edge("patch", END)
        return graph.compile()

    if run_mode == "validation":
        graph.add_node("patch", patch_node)
        graph.add_node("validation", validation_node)
        if analysis_ready:
            graph.add_edge(START, "patch")
        else:
            graph.add_node("analysis", analysis_node)
            graph.add_edge(START, "analysis")
            graph.add_edge("analysis", "patch")
        graph.add_edge("patch", "validation")
        graph.add_edge("validation", END)
        return graph.compile()

    graph.add_node("triage", triage_node)
    graph.add_node("analysis", analysis_node)
    graph.add_node("patch", patch_node)
    graph.add_node("validation", validation_node)
    graph.add_edge(START, "triage")
    graph.add_edge("triage", "analysis")
    graph.add_edge("analysis", "patch")
    graph.add_edge("patch", "validation")
    graph.add_edge("validation", END)
    return graph.compile()


def run_workflow(
    initial_state: PatchWorkflowState,
    config: AppConfig,
    build_triage_agent: Callable[[AppConfig], Any],
    build_analysis_agent: Callable[[AppConfig], Any],
    build_patch_agent: Callable[[AppConfig], Any],
    build_validation_agent: Callable[[AppConfig], Any],
    run_mode: str = "full",
) -> PatchWorkflowState:
    """Execute the LangGraph workflow and return the updated shared state."""

    workflow = build_workflow(
        config=config,
        build_triage_agent=build_triage_agent,
        build_analysis_agent=build_analysis_agent,
        build_patch_agent=build_patch_agent,
        build_validation_agent=build_validation_agent,
        run_mode=run_mode,
        analysis_ready=initial_state.analysis_output is not None and bool(initial_state.repository_findings),
    )
    result = workflow.invoke(_state_to_dict(initial_state))
    return _dict_to_state(result)
