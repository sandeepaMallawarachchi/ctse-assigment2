"""Shared configuration helpers for the local MAS project.

This module will later centralize environment-driven settings such as
Ollama model names, output paths, and logging configuration.
"""

from dataclasses import dataclass
import os


@dataclass(slots=True)
class AppConfig:
    """Minimal application configuration container."""

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    patch_agent_model: str = os.getenv("PATCH_AGENT_MODEL", "llama3.1")
