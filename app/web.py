"""Minimal local web server for the MAS frontend demo."""

from __future__ import annotations

import argparse
import cgi
import json
import logging
import shutil
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import AppConfig
from app.main import (
    build_result_payload,
    build_state_from_issue_payload,
    configure_logging,
    execute_run_mode,
)
from tools.patch_tools.patch_writer import (
    build_fixed_file_preview,
    write_fixed_file_preview,
)
STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"


def _guess_content_type(path: Path) -> str:
    """Return a simple content type for static frontend files."""

    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"


def _safe_text(field: Any, default: str = "") -> str:
    """Extract text safely from a CGI field."""

    if field is None:
        return default
    value = getattr(field, "value", field)
    if value is None:
        return default
    return str(value).strip() or default


def _load_issue_payload_from_form(form: cgi.FieldStorage) -> dict[str, Any]:
    """Build issue payload from manual form fields."""

    issue_id = _safe_text(
        form["issue_id"] if "issue_id" in form else None,
        default=f"ISSUE-{uuid.uuid4().hex[:8].upper()}",
    )
    title = _safe_text(
        form["issue_title"] if "issue_title" in form else None,
    )
    description = _safe_text(
        form["issue_description"] if "issue_description" in form else None,
    )
    expected_behavior = _safe_text(
        form["expected_behavior"] if "expected_behavior" in form else None,
        default="",
    ) or None

    if not title or not description:
        raise ValueError("Issue title and description are required.")

    return {
        "issue_id": issue_id,
        "title": title,
        "description": description,
        "expected_behavior": expected_behavior,
    }


def _read_text_file(path: Path) -> str:
    """Read a text file safely for frontend preview rendering."""

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Uploaded file must be a UTF-8 text file for preview and patch generation."
        ) from exc


def _build_file_preview_payload(
    uploaded_path: Path | None,
    state: Any,
    patch_output_dir: str,
) -> dict[str, Any] | None:
    """Build original/fixed file preview data for the frontend."""

    if uploaded_path is None:
        return None

    original_content = _read_text_file(uploaded_path)
    payload: dict[str, Any] = {
        "original_filename": uploaded_path.name,
        "original_content": original_content,
    }

    if state.patch_agent_output is None:
        return payload

    fixed_content = build_fixed_file_preview(
        original_content=original_content,
        original_filename=uploaded_path.name,
        proposal=state.patch_agent_output.proposal,
    )
    fixed_file_path = write_fixed_file_preview(
        issue_id=state.patch_agent_output.proposal.issue_id,
        original_filename=uploaded_path.name,
        fixed_content=fixed_content,
        output_dir=patch_output_dir,
    )
    payload.update(
        {
            "fixed_filename": Path(fixed_file_path).name,
            "fixed_content": fixed_content,
            "fixed_file_path": fixed_file_path,
        }
    )
    return payload


class FrontendHandler(BaseHTTPRequestHandler):
    """Serve the upload UI and execute local agent flows."""

    server_version = "LocalMASDemo/1.0"

    def do_GET(self) -> None:
        """Serve the frontend or static assets."""

        if self.path in {"/", "/index.html"}:
            self._serve_static(STATIC_DIR / "index.html")
            return
        if self.path.startswith("/static/"):
            relative = self.path.removeprefix("/static/")
            self._serve_static(STATIC_DIR / relative)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        """Handle frontend submissions and run the requested agents."""

        if self.path != "/api/run":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            response_payload = self._handle_run_request()
        except Exception as exc:  # noqa: BLE001 - UI should receive structured error details
            logging.getLogger(__name__).exception("Web request failed")
            self._send_json(
                {
                    "ok": False,
                    "error": str(exc),
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        self._send_json(response_payload, status=HTTPStatus.OK)

    def log_message(self, format: str, *args: object) -> None:
        """Route request logs through the standard logging system."""

        logging.getLogger(__name__).info("HTTP %s", format % args)

    def _serve_static(self, path: Path) -> None:
        """Serve one static file from the frontend directory."""

        try:
            resolved_path = path.resolve(strict=True)
            static_root = STATIC_DIR.resolve(strict=True)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "Static file not found")
            return

        if static_root not in resolved_path.parents and resolved_path != static_root:
            self.send_error(HTTPStatus.FORBIDDEN, "Static path is outside the frontend directory")
            return

        if not resolved_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Static file not found")
            return

        content = resolved_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _guess_content_type(resolved_path))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus) -> None:
        """Send a JSON response to the frontend."""

        content = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_run_request(self) -> dict[str, Any]:
        """Parse the form submission and execute the requested flow."""

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            },
        )

        run_mode = _safe_text(form.getfirst("run_mode"), "full")
        if run_mode not in {"triage", "analysis", "patch", "validation", "full"}:
            raise ValueError("Invalid run mode selected.")

        issue_payload = _load_issue_payload_from_form(form)

        upload_field = form["code_file"] if "code_file" in form else None
        saved_file_path = self._save_uploaded_file(upload_field)
        repo_root = (
            str(saved_file_path.parent)
            if saved_file_path is not None
            else _safe_text(
                form["repo_root"] if "repo_root" in form else None,
                "data/repo_mock",
            )
        )

        config = AppConfig()
        state = build_state_from_issue_payload(
            issue_payload=issue_payload,
            repo_root=repo_root,
            code_file=str(saved_file_path) if saved_file_path is not None else None,
        )
        updated_state = execute_run_mode(
            run_mode=run_mode,
            state=state,
            config=config,
            analysis_artifact_path=None,
            emit_console=False,
        )
        result_payload = build_result_payload(run_mode, updated_state)
        file_preview = _build_file_preview_payload(
            uploaded_path=saved_file_path,
            state=updated_state,
            patch_output_dir=config.patch_output_dir,
        )

        return {
            "ok": True,
            "uploaded_file": str(saved_file_path) if saved_file_path is not None else None,
            "result": result_payload,
            "file_preview": file_preview,
        }

    def _save_uploaded_file(self, upload_field: Any) -> Path | None:
        """Persist one uploaded code file into the local upload directory."""

        if upload_field is None or not getattr(upload_field, "filename", None):
            return None

        original_name = Path(str(upload_field.filename)).name
        if not original_name:
            return None

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        session_dir = UPLOAD_DIR / uuid.uuid4().hex
        session_dir.mkdir(parents=True, exist_ok=True)
        target_path = session_dir / original_name
        with target_path.open("wb") as file_handle:
            shutil.copyfileobj(upload_field.file, file_handle)
        return target_path


def run_web_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the local demo web server."""

    config = AppConfig()
    configure_logging(config)
    logging.getLogger(__name__).info("Starting web UI at http://%s:%d", host, port)
    server = ThreadingHTTPServer((host, port), FrontendHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopping web UI")
    finally:
        server.server_close()


def parse_web_args() -> argparse.Namespace:
    """Parse optional host and port flags for the local web server."""

    parser = argparse.ArgumentParser(description="Run the local MAS web frontend.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_web_args()
    run_web_server(host=args.host, port=args.port)
