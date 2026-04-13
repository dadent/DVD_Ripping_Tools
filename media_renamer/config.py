"""Configuration management — loads .env and config.yaml, provides AppConfig."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from dotenv import load_dotenv
import yaml
import os


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

_DEFAULT_DURATION_TOLERANCE_MIN = 3.0
_DEFAULT_BONUS_THRESHOLD_MIN = 10.0
_DEFAULT_PLAY_ALL_TOLERANCE_MIN = 5.0


# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Application configuration assembled from .env + config.yaml."""

    # API keys (from .env / environment)
    tmdb_api_key: str = ""
    openai_api_key: str = ""

    # Paths (from CLI args, not config file)
    source_dir: Path | None = None
    dest_dir: Path | None = None
    dry_run: bool = False

    # Matching settings
    duration_tolerance_min: float = Field(
        default=_DEFAULT_DURATION_TOLERANCE_MIN,
        description="Allowed ± difference (minutes) when matching MKV durations to episode runtimes",
    )
    bonus_threshold_min: float = Field(
        default=_DEFAULT_BONUS_THRESHOLD_MIN,
        description="Files shorter than this (minutes) are classified as bonus content",
    )
    play_all_tolerance_min: float = Field(
        default=_DEFAULT_PLAY_ALL_TOLERANCE_MIN,
        description="Allowed ± difference (minutes) when detecting Play All tracks",
    )

    # LLM
    openai_model: str | None = Field(
        default=None,
        description="Override OpenAI model; None = auto-detect best available",
    )


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning an empty dict if missing or invalid."""
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        # Malformed YAML, encoding errors, file deleted between check and open
        return {}


def _safe_float(value, default: float) -> float:
    """Convert a value to float, returning *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_config(
    *,
    env_file: Path | None = None,
    config_file: Path | None = None,
    source_dir: Path | None = None,
    dest_dir: Path | None = None,
    dry_run: bool = False,
) -> AppConfig:
    """Build an AppConfig from environment variables + optional config.yaml.

    Priority (highest → lowest):
      1. Explicit keyword arguments (source_dir, dest_dir, dry_run)
      2. Environment variables / .env (API keys)
      3. config.yaml (matching settings, model override)
      4. Built-in defaults
    """
    # --- .env ---
    if env_file and env_file.is_file():
        load_dotenv(env_file)
    else:
        load_dotenv()  # auto-find .env in cwd / parents

    # --- config.yaml ---
    yaml_data: dict = {}
    if config_file:
        yaml_data = _load_yaml(config_file)
    else:
        candidate = Path.cwd() / "config.yaml"
        if candidate.is_file():
            yaml_data = _load_yaml(candidate)

    return AppConfig(
        tmdb_api_key=os.getenv("TMDB_API_KEY", yaml_data.get("tmdb_api_key", "")),
        openai_api_key=os.getenv("OPENAI_API_KEY", yaml_data.get("openai_api_key", "")),
        source_dir=source_dir,
        dest_dir=dest_dir,
        dry_run=dry_run,
        duration_tolerance_min=_safe_float(
            yaml_data.get("duration_tolerance_min"), _DEFAULT_DURATION_TOLERANCE_MIN,
        ),
        bonus_threshold_min=_safe_float(
            yaml_data.get("bonus_threshold_min"), _DEFAULT_BONUS_THRESHOLD_MIN,
        ),
        play_all_tolerance_min=_safe_float(
            yaml_data.get("play_all_tolerance_min"), _DEFAULT_PLAY_ALL_TOLERANCE_MIN,
        ),
        openai_model=yaml_data.get("openai_model"),
    )
