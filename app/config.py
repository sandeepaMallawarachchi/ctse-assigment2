"""Shared configuration helpers for the local MAS project.

This module will later centralize environment-driven settings such as
Ollama model names, output paths, and logging configuration.
"""

from dataclasses import dataclass
import os


@dataclass
class AppConfig:
    """Minimal application configuration container."""

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    triage_agent_model: str = os.getenv("TRIAGE_AGENT_MODEL", "llama3.1")
    use_ollama_for_triage_agent: bool = (
        os.getenv("USE_OLLAMA_FOR_TRIAGE_AGENT", "true").strip().lower() == "true"
    )
    triage_output_dir: str = os.getenv("TRIAGE_OUTPUT_DIR", "outputs/reports")
    allow_triage_fallback: bool = (
        os.getenv("ALLOW_TRIAGE_FALLBACK", "true").strip().lower() == "true"
    )
    analysis_agent_model: str = os.getenv("ANALYSIS_AGENT_MODEL", "llama3.1")
    use_ollama_for_analysis_agent: bool = (
        os.getenv("USE_OLLAMA_FOR_ANALYSIS_AGENT", "true").strip().lower() == "true"
    )
    analysis_output_dir: str = os.getenv("ANALYSIS_OUTPUT_DIR", "outputs/reports")
    allow_analysis_fallback: bool = (
        os.getenv("ALLOW_ANALYSIS_FALLBACK", "true").strip().lower() == "true"
    )
    patch_agent_model: str = os.getenv("PATCH_AGENT_MODEL", "llama3.1")
    use_ollama_for_patch_agent: bool = (
        os.getenv("USE_OLLAMA_FOR_PATCH_AGENT", "true").strip().lower() == "true"
    )
    patch_output_dir: str = os.getenv("PATCH_OUTPUT_DIR", "outputs/patches")
    allow_patch_fallback: bool = (
        os.getenv("ALLOW_PATCH_FALLBACK", "true").strip().lower() == "true"
    )
    execution_log_path: str = os.getenv("EXECUTION_LOG_PATH", "logs/execution.log")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
