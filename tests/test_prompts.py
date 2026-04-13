"""Tests for media_renamer.prompts — LLM client, prompts, and fallback parsing."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from media_renamer.config import AppConfig
from media_renamer.prompts import (
    FolderInterpretation,
    LLMClient,
    auto_detect_model,
    parse_folder_name_fallback,
)


# ---------------------------------------------------------------------------
# Fallback regex parsing
# ---------------------------------------------------------------------------


class TestFallbackParser:
    def test_standard_season_disc(self):
        result = parse_folder_name_fallback("GILMORE_GIRLS_S1_US_D1")
        assert result.title == "Gilmore Girls"
        assert result.season == 1
        assert result.disc == 1
        assert result.content_type == "tv"

    def test_no_region_code(self):
        result = parse_folder_name_fallback("GILMORE_GIRLS_S2_D1")
        assert result.title == "Gilmore Girls"
        assert result.season == 2
        assert result.disc == 1

    def test_disc_as_word(self):
        result = parse_folder_name_fallback("GILMOREGIRLS_S2_DISC4")
        assert result.season == 2
        assert result.disc == 4
        assert result.content_type == "tv"

    def test_season_as_word(self):
        result = parse_folder_name_fallback("GILMORE GIRLS SEASON ONE DISC 1")
        assert result.season == 1
        assert result.disc == 1
        assert result.content_type == "tv"

    def test_movie_no_season(self):
        result = parse_folder_name_fallback("THE_MATRIX")
        assert result.season is None
        assert result.disc is None
        assert result.content_type == "unknown"
        assert "Matrix" in result.title

    def test_friends_pattern(self):
        result = parse_folder_name_fallback("FRIENDS_S2_D3")
        assert result.title == "Friends"
        assert result.season == 2
        assert result.disc == 3

    def test_band_of_brothers(self):
        result = parse_folder_name_fallback("BAND_OF_BROTHERS_D2")
        assert "Band Of Brothers" in result.title
        assert result.disc == 2

    def test_confidence_is_low(self):
        """Fallback should always report low confidence."""
        result = parse_folder_name_fallback("ANYTHING")
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# Model auto-detection (mocked)
# ---------------------------------------------------------------------------


class TestAutoDetectModel:
    def test_prefers_gpt4o_mini(self):
        mock_client = MagicMock()
        mock_client.models.list.return_value = [
            SimpleNamespace(id="gpt-4o-mini"),
            SimpleNamespace(id="gpt-4o"),
            SimpleNamespace(id="gpt-5"),
        ]
        assert auto_detect_model(mock_client) == "gpt-4o-mini"

    def test_falls_back_to_next_preferred(self):
        mock_client = MagicMock()
        mock_client.models.list.return_value = [
            SimpleNamespace(id="gpt-4o"),
            SimpleNamespace(id="gpt-3.5-turbo"),
        ]
        assert auto_detect_model(mock_client) == "gpt-4o"

    def test_handles_api_error(self):
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("API error")
        assert auto_detect_model(mock_client) == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# LLMClient — mocked OpenAI responses
# ---------------------------------------------------------------------------

def _mock_chat_response(content: str):
    """Build a mock OpenAI chat completion response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class TestLLMClientFolderInterpretation:
    @patch("media_renamer.prompts.OpenAI")
    @patch("media_renamer.prompts.auto_detect_model", return_value="gpt-4o-mini")
    def test_interprets_tv_folder(self, mock_detect, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_client.chat.completions.create.return_value = _mock_chat_response(
            json.dumps({
                "title": "Gilmore Girls",
                "season": 1,
                "disc": 1,
                "content_type": "tv",
                "confidence": "high",
                "notes": "Region code US ignored",
            })
        )

        config = AppConfig(openai_api_key="fake")
        llm = LLMClient(config)
        result = llm.interpret_folder_name("GILMORE_GIRLS_S1_US_D1")

        assert result.title == "Gilmore Girls"
        assert result.season == 1
        assert result.disc == 1
        assert result.content_type == "tv"
        assert result.confidence == "high"

    @patch("media_renamer.prompts.OpenAI")
    @patch("media_renamer.prompts.auto_detect_model", return_value="gpt-4o-mini")
    def test_interprets_movie_folder(self, mock_detect, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_client.chat.completions.create.return_value = _mock_chat_response(
            json.dumps({
                "title": "The Matrix",
                "season": None,
                "disc": None,
                "content_type": "movie",
                "confidence": "high",
                "notes": "",
            })
        )

        config = AppConfig(openai_api_key="fake")
        llm = LLMClient(config)
        result = llm.interpret_folder_name("THE_MATRIX")

        assert result.title == "The Matrix"
        assert result.content_type == "movie"
        assert result.season is None

    @patch("media_renamer.prompts.OpenAI")
    @patch("media_renamer.prompts.auto_detect_model", return_value="gpt-4o-mini")
    def test_falls_back_on_api_error(self, mock_detect, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API down")

        config = AppConfig(openai_api_key="fake")
        llm = LLMClient(config)
        result = llm.interpret_folder_name("FRIENDS_S2_D3")

        # Should fall back to regex parser
        assert result.title == "Friends"
        assert result.season == 2
        assert result.disc == 3
        assert result.confidence == "low"


class TestLLMClientExtraClassification:
    @patch("media_renamer.prompts.OpenAI")
    @patch("media_renamer.prompts.auto_detect_model", return_value="gpt-4o-mini")
    def test_classifies_extra(self, mock_detect, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_client.chat.completions.create.return_value = _mock_chat_response(
            json.dumps({
                "extra_type": "featurette",
                "label": "Behind the scenes featurette",
                "confidence": "medium",
            })
        )

        config = AppConfig(openai_api_key="fake")
        llm = LLMClient(config)
        result = llm.classify_extra("DISC6-B3_t03.mkv", 2.3, "Gilmore Girls")

        assert result.extra_type == "featurette"
        assert result.confidence == "medium"

    @patch("media_renamer.prompts.OpenAI")
    @patch("media_renamer.prompts.auto_detect_model", return_value="gpt-4o-mini")
    def test_falls_back_on_error(self, mock_detect, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API down")

        config = AppConfig(openai_api_key="fake")
        llm = LLMClient(config)
        result = llm.classify_extra("unknown_clip.mkv", 3.0)

        assert result.extra_type == "other"
        assert result.confidence == "low"
