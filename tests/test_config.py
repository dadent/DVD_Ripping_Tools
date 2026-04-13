"""Tests for media_renamer.config — configuration loading."""

import os
import textwrap
from pathlib import Path

import pytest

from media_renamer.config import AppConfig, load_config


# ---------------------------------------------------------------------------
# AppConfig defaults
# ---------------------------------------------------------------------------


class TestAppConfigDefaults:
    def test_default_values(self):
        cfg = AppConfig()
        assert cfg.tmdb_api_key == ""
        assert cfg.openai_api_key == ""
        assert cfg.source_dir is None
        assert cfg.dest_dir is None
        assert cfg.dry_run is False
        assert cfg.duration_tolerance_min == 3.0
        assert cfg.bonus_threshold_min == 10.0
        assert cfg.play_all_tolerance_min == 5.0
        assert cfg.openai_model is None


# ---------------------------------------------------------------------------
# load_config — from .env
# ---------------------------------------------------------------------------


class TestLoadConfigEnv:
    def test_loads_env_vars(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TMDB_API_KEY=test_tmdb_key\nOPENAI_API_KEY=test_openai_key\n"
        )
        # Clear any pre-existing env vars
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        cfg = load_config(env_file=env_file)
        assert cfg.tmdb_api_key == "test_tmdb_key"
        assert cfg.openai_api_key == "test_openai_key"

    def test_env_vars_override(self, monkeypatch):
        monkeypatch.setenv("TMDB_API_KEY", "from_env")
        monkeypatch.setenv("OPENAI_API_KEY", "from_env_2")

        cfg = load_config()
        assert cfg.tmdb_api_key == "from_env"
        assert cfg.openai_api_key == "from_env_2"


# ---------------------------------------------------------------------------
# load_config — from config.yaml
# ---------------------------------------------------------------------------


class TestLoadConfigYaml:
    def test_loads_yaml_settings(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
                duration_tolerance_min: 5.0
                bonus_threshold_min: 15.0
                play_all_tolerance_min: 8.0
                openai_model: gpt-4o-mini
            """)
        )
        cfg = load_config(config_file=yaml_file)
        assert cfg.duration_tolerance_min == 5.0
        assert cfg.bonus_threshold_min == 15.0
        assert cfg.play_all_tolerance_min == 8.0
        assert cfg.openai_model == "gpt-4o-mini"

    def test_missing_yaml_uses_defaults(self, monkeypatch):
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        cfg = load_config(config_file=Path("nonexistent.yaml"))
        assert cfg.duration_tolerance_min == 3.0
        assert cfg.bonus_threshold_min == 10.0

    def test_empty_yaml_uses_defaults(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("")
        cfg = load_config(config_file=yaml_file)
        assert cfg.duration_tolerance_min == 3.0


# ---------------------------------------------------------------------------
# load_config — CLI args
# ---------------------------------------------------------------------------


class TestLoadConfigCliArgs:
    def test_source_dest_passthrough(self, monkeypatch):
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        cfg = load_config(
            source_dir=Path("D:/rips"),
            dest_dir=Path("D:/staging"),
            dry_run=True,
        )
        assert cfg.source_dir == Path("D:/rips")
        assert cfg.dest_dir == Path("D:/staging")
        assert cfg.dry_run is True
