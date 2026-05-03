# Automated Software Issue Resolver

Local multi-agent system (MAS) assignment project that resolves software issues
through a connected workflow of specialized agents. The current implementation
uses LangGraph for orchestration, Ollama-compatible agent adapters, shared
structured state, custom Python tools, local logging, and evaluation scripts.

Current runnable modes:
- `python3 app/main.py` then choose `1`, `2`, `3`, `4`, or `5`
- `python3 app/main.py --run triage`
- `python3 app/main.py --run analysis --repo-root data/repo_mock`
- `python3 app/main.py --run patch`
- `python3 app/main.py --run validation`
- `python3 app/main.py --run patch --analysis-artifact outputs/reports/ISSUE-001_analysis.json`
- `python3 app/main.py --run full --repo-root data/repo_mock`

Frontend demo:
- `python3 app/web.py`
- Open `http://127.0.0.1:8000`
- Enter issue details, upload a local code file, choose one agent or the full flow, and review the structured outputs on the page

LangGraph orchestration:
- `orchestrator/graph.py` contains the connected LangGraph workflow
- `full` flow runs `triage -> analysis -> patch -> validation`
- `patch` and `validation` modes also use graph-managed state transitions

Evaluation:
- `PYTHONPATH=. python3 tests/evaluate_workflow.py`
- writes `outputs/reports/evaluation_summary.json`
- provides small local evidence that the connected workflow completes across sample cases

Single-file runs from CLI:
- `python3 app/main.py --run analysis --repo-root /path/to/project --code-file /path/to/project/src/example.py`
- `python3 app/main.py --run full --repo-root /path/to/project --code-file /path/to/project/src/example.py`
