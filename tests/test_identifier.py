"""Tests for media_renamer.identifier — TMDb client and content classification."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from media_renamer.config import AppConfig
from media_renamer.identifier import (
    TMDbClient,
    classify_content_type,
)
from media_renamer.models import (
    ContentType,
    DiscFolder,
    FileClassification,
    MediaFile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mf(name: str, duration_min: float, classification: FileClassification = FileClassification.EPISODE) -> MediaFile:
    return MediaFile(
        path=Path(f"/fake/{name}"),
        filename=name,
        duration_seconds=duration_min * 60,
        classification=classification,
    )


def _folder(name: str, files: list[MediaFile]) -> DiscFolder:
    return DiscFolder(path=Path(f"/fake/{name}"), name=name, files=files)


def _default_config(**overrides) -> AppConfig:
    return AppConfig(**overrides)


# ---------------------------------------------------------------------------
# TMDb client — mocked
# ---------------------------------------------------------------------------

def _mock_movie_search_result(**kwargs):
    return SimpleNamespace(
        id=kwargs.get("id", 603),
        title=kwargs.get("title", "The Matrix"),
        release_date=kwargs.get("release_date", "1999-03-31"),
        overview=kwargs.get("overview", "A computer hacker..."),
    )


def _mock_tv_search_result(**kwargs):
    return SimpleNamespace(
        id=kwargs.get("id", 4586),
        name=kwargs.get("name", "Gilmore Girls"),
        first_air_date=kwargs.get("first_air_date", "2000-10-05"),
        overview=kwargs.get("overview", "A drama about..."),
    )


def _mock_movie_details(**kwargs):
    return SimpleNamespace(
        title=kwargs.get("title", "The Matrix"),
        release_date=kwargs.get("release_date", "1999-03-31"),
        runtime=kwargs.get("runtime", 136),
    )


def _mock_tv_details(**kwargs):
    return SimpleNamespace(
        name=kwargs.get("name", "Gilmore Girls"),
        first_air_date=kwargs.get("first_air_date", "2000-10-05"),
    )


def _mock_season_details(episodes):
    eps = [
        SimpleNamespace(
            episode_number=ep["num"],
            name=ep["name"],
            runtime=ep.get("runtime"),
        )
        for ep in episodes
    ]
    return SimpleNamespace(episodes=eps)


def _mock_external_ids(**kwargs):
    return SimpleNamespace(**kwargs)


class TestTMDbClientSearch:
    @patch("media_renamer.identifier.Movie")
    @patch("media_renamer.identifier.TV")
    @patch("media_renamer.identifier.Season")
    @patch("media_renamer.identifier.TMDb")
    def test_search_movie(self, mock_tmdb_cls, mock_season_cls, mock_tv_cls, mock_movie_cls):
        mock_movie = MagicMock()
        mock_movie.search.return_value = [
            _mock_movie_search_result(id=603, title="The Matrix", release_date="1999-03-31"),
            _mock_movie_search_result(id=604, title="The Matrix Reloaded", release_date="2003-05-15"),
        ]
        mock_movie_cls.return_value = mock_movie

        client = TMDbClient(api_key="fake_key")
        results = client.search_movie("The Matrix")

        assert len(results) == 2
        assert results[0].tmdb_id == 603
        assert results[0].title == "The Matrix"
        assert results[0].year == 1999
        assert results[1].year == 2003

    @patch("media_renamer.identifier.Movie")
    @patch("media_renamer.identifier.TV")
    @patch("media_renamer.identifier.Season")
    @patch("media_renamer.identifier.TMDb")
    def test_search_tv(self, mock_tmdb_cls, mock_season_cls, mock_tv_cls, mock_movie_cls):
        mock_tv = MagicMock()
        mock_tv.search.return_value = [
            _mock_tv_search_result(id=4586, name="Gilmore Girls", first_air_date="2000-10-05"),
        ]
        mock_tv_cls.return_value = mock_tv

        client = TMDbClient(api_key="fake_key")
        results = client.search_tv("Gilmore Girls")

        assert len(results) == 1
        assert results[0].tmdb_id == 4586
        assert results[0].title == "Gilmore Girls"
        assert results[0].first_air_year == 2000

    @patch("media_renamer.identifier.Movie")
    @patch("media_renamer.identifier.TV")
    @patch("media_renamer.identifier.Season")
    @patch("media_renamer.identifier.TMDb")
    def test_search_movie_error_returns_empty(self, mock_tmdb_cls, mock_season_cls, mock_tv_cls, mock_movie_cls):
        mock_movie = MagicMock()
        mock_movie.search.side_effect = Exception("API error")
        mock_movie_cls.return_value = mock_movie

        client = TMDbClient(api_key="fake_key")
        results = client.search_movie("anything")
        assert results == []


class TestTMDbClientDetails:
    @patch("media_renamer.identifier.Movie")
    @patch("media_renamer.identifier.TV")
    @patch("media_renamer.identifier.Season")
    @patch("media_renamer.identifier.TMDb")
    def test_get_movie_details(self, mock_tmdb_cls, mock_season_cls, mock_tv_cls, mock_movie_cls):
        mock_movie = MagicMock()
        mock_movie.details.return_value = _mock_movie_details(
            title="The Matrix", release_date="1999-03-31", runtime=136
        )
        mock_movie.external_ids.return_value = _mock_external_ids(imdb_id="tt0133093")
        mock_movie_cls.return_value = mock_movie

        client = TMDbClient(api_key="fake_key")
        match = client.get_movie_details(603)

        assert match is not None
        assert match.tmdb_id == 603
        assert match.title == "The Matrix"
        assert match.year == 1999
        assert match.runtime_minutes == 136
        assert match.imdb_id == "tt0133093"

    @patch("media_renamer.identifier.Movie")
    @patch("media_renamer.identifier.TV")
    @patch("media_renamer.identifier.Season")
    @patch("media_renamer.identifier.TMDb")
    def test_get_season_episodes(self, mock_tmdb_cls, mock_season_cls, mock_tv_cls, mock_movie_cls):
        mock_season = MagicMock()
        mock_season.details.return_value = _mock_season_details([
            {"num": 1, "name": "Pilot", "runtime": 44},
            {"num": 2, "name": "The Lorelais' First Day at Chilton", "runtime": 43},
            {"num": 3, "name": "Kill Me Now", "runtime": 43},
        ])
        mock_season_cls.return_value = mock_season

        client = TMDbClient(api_key="fake_key")
        episodes = client.get_season_episodes(4586, 1)

        assert len(episodes) == 3
        assert episodes[0].episode_number == 1
        assert episodes[0].title == "Pilot"
        assert episodes[0].runtime_minutes == 44
        assert episodes[1].runtime_minutes == 43

    @patch("media_renamer.identifier.Movie")
    @patch("media_renamer.identifier.TV")
    @patch("media_renamer.identifier.Season")
    @patch("media_renamer.identifier.TMDb")
    def test_get_tv_external_ids(self, mock_tmdb_cls, mock_season_cls, mock_tv_cls, mock_movie_cls):
        mock_tv = MagicMock()
        mock_tv.external_ids.return_value = _mock_external_ids(
            imdb_id="tt0238784", tvdb_id=76568
        )
        mock_tv_cls.return_value = mock_tv

        client = TMDbClient(api_key="fake_key")
        ext = client.get_tv_external_ids(4586)

        assert ext["imdb_id"] == "tt0238784"
        assert ext["tvdb_id"] == 76568

    @patch("media_renamer.identifier.Movie")
    @patch("media_renamer.identifier.TV")
    @patch("media_renamer.identifier.Season")
    @patch("media_renamer.identifier.TMDb")
    def test_build_tv_match(self, mock_tmdb_cls, mock_season_cls, mock_tv_cls, mock_movie_cls):
        mock_tv = MagicMock()
        mock_tv.details.return_value = _mock_tv_details(
            name="Gilmore Girls", first_air_date="2000-10-05"
        )
        mock_tv.external_ids.return_value = _mock_external_ids(
            imdb_id="tt0238784", tvdb_id=76568
        )
        mock_tv_cls.return_value = mock_tv

        client = TMDbClient(api_key="fake_key")
        match = client.build_tv_match(4586, 1)

        assert match is not None
        assert match.tmdb_id == 4586
        assert match.tvdb_id == 76568
        assert match.title == "Gilmore Girls"
        assert match.year == 2000
        assert match.season_number == 1


# ---------------------------------------------------------------------------
# Content type classification
# ---------------------------------------------------------------------------


class TestClassifyContentType:
    def test_tv_series_multiple_similar_episodes(self):
        """Multiple files with similar durations → TV_SERIES."""
        folder = _folder("DISC1", [
            _mf("ep1.mkv", 44.0),
            _mf("ep2.mkv", 43.0),
            _mf("ep3.mkv", 44.5),
            _mf("ep4.mkv", 42.0),
            _mf("playall.mkv", 175.0, FileClassification.PLAY_ALL),
        ])
        assert classify_content_type(folder, _default_config()) == ContentType.TV_SERIES

    def test_movie_single_long_file_plus_extras(self):
        """One long file + short bonus files → MOVIE."""
        folder = _folder("THE_MATRIX", [
            _mf("main.mkv", 136.0),
            _mf("trailer.mkv", 3.0, FileClassification.BONUS),
            _mf("bts.mkv", 5.0, FileClassification.BONUS),
        ])
        assert classify_content_type(folder, _default_config()) == ContentType.MOVIE

    def test_unknown_when_no_episode_files(self):
        """All files are bonus → UNKNOWN."""
        folder = _folder("MYSTERY", [
            _mf("clip1.mkv", 2.0, FileClassification.BONUS),
            _mf("clip2.mkv", 3.0, FileClassification.BONUS),
        ])
        assert classify_content_type(folder, _default_config()) == ContentType.UNKNOWN

    def test_unknown_when_mixed_durations(self):
        """Files with very different durations → UNKNOWN."""
        folder = _folder("MIXED", [
            _mf("a.mkv", 120.0),
            _mf("b.mkv", 22.0),
            _mf("c.mkv", 45.0),
        ])
        assert classify_content_type(folder, _default_config()) == ContentType.UNKNOWN

    def test_two_similar_episodes_is_tv(self):
        """Even 2 similar-length files could be TV (final disc of season)."""
        folder = _folder("DISC6", [
            _mf("ep1.mkv", 43.8),
            _mf("ep2.mkv", 44.9),
            _mf("bonus.mkv", 5.4, FileClassification.BONUS),
        ])
        # 2 files — need ≥3 for TV, so this could go either way
        # With 2 files our heuristic says UNKNOWN since it's ambiguous
        result = classify_content_type(folder, _default_config())
        # 2 is still multiple, and they're similar — should be TV_SERIES
        assert result == ContentType.TV_SERIES
