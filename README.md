# Automated Software Issue Resolver

Starter scaffold for a multi-agent system (MAS) assignment that resolves software issues locally using agentic AI patterns.

Current scope:
- shared project structure
- Triage Agent starter files
- Codebase Analysis Agent starter files
- Patch Generation Agent starter files
- minimal placeholders for orchestration, app entrypoint, tools, and tests

This repository is intentionally kept minimal for step-by-step development.

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

Single-file runs from CLI:
- `python3 app/main.py --run analysis --repo-root /path/to/project --code-file /path/to/project/src/example.py`
- `python3 app/main.py --run full --repo-root /path/to/project --code-file /path/to/project/src/example.py`
