"""Tests for media_renamer.ui formatting helpers and path builders."""

from __future__ import annotations

from pathlib import Path

import pytest

from media_renamer.models import (
    EpisodeInfo,
    EpisodeMatch,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
    TVShowMatch,
)
from media_renamer.ui import (
    SessionStats,
    format_confidence,
    format_duration,
    _classification_icon,
)
from media_renamer.cli import (
    _movie_path,
    _tv_episode_path,
    _tv_extra_path,
    _parse_disc_number,
)


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_minutes_and_seconds(self):
        assert format_duration(125) == "2:05"

    def test_hours(self):
        assert format_duration(3661) == "1:01:01"

    def test_zero(self):
        assert format_duration(0) == "0:00"

    def test_exact_hour(self):
        assert format_duration(3600) == "1:00:00"

    def test_under_a_minute(self):
        assert format_duration(45) == "0:45"


# ---------------------------------------------------------------------------
# format_confidence
# ---------------------------------------------------------------------------

class TestFormatConfidence:
    def test_high(self):
        result = format_confidence(MatchConfidence.HIGH)
        assert "HIGH" in result
        assert "green" in result

    def test_medium(self):
        result = format_confidence(MatchConfidence.MEDIUM)
        assert "MED" in result
        assert "yellow" in result

    def test_low(self):
        result = format_confidence(MatchConfidence.LOW)
        assert "LOW" in result
        assert "red" in result


# ---------------------------------------------------------------------------
# Classification icons
# ---------------------------------------------------------------------------

class TestClassificationIcon:
    def test_episode(self):
        assert _classification_icon(FileClassification.EPISODE) == "📺"

    def test_play_all(self):
        assert _classification_icon(FileClassification.PLAY_ALL) == "⏭️"

    def test_bonus(self):
        assert _classification_icon(FileClassification.BONUS) == "📦"


# ---------------------------------------------------------------------------
# Plex path builders
# ---------------------------------------------------------------------------

def _make_ep_match(season: int, ep_num: int, title: str) -> EpisodeMatch:
    return EpisodeMatch(
        file=MediaFile(
            path=Path("/fake/file.mkv"),
            filename="file.mkv",
            duration_seconds=2640,
        ),
        episode=EpisodeInfo(
            season_number=season,
            episode_number=ep_num,
            title=title,
        ),
        confidence=MatchConfidence.HIGH,
    )


class TestTvEpisodePath:
    def test_basic_path(self):
        show = TVShowMatch(
            tmdb_id=4586,
            tvdb_id=76568,
            title="Gilmore Girls",
            year=2000,
            season_number=1,
        )
        em = _make_ep_match(1, 1, "Pilot")
        path = _tv_episode_path(show, em)

        assert path == (
            "TV Shows/Gilmore Girls (2000) {tvdb-76568}/"
            "Season 01/"
            "Gilmore Girls (2000) - s01e01 - Pilot.mkv"
        )

    def test_no_year(self):
        show = TVShowMatch(tmdb_id=1, title="TestShow", season_number=2)
        em = _make_ep_match(2, 5, "Test Episode")
        path = _tv_episode_path(show, em)
        assert "TestShow - s02e05 - Test Episode.mkv" in path
        assert "{tvdb-" not in path  # no tvdb_id

    def test_two_digit_padding(self):
        show = TVShowMatch(tmdb_id=1, tvdb_id=123, title="Show", year=2020, season_number=1)
        em = _make_ep_match(1, 9, "Ep Nine")
        path = _tv_episode_path(show, em)
        assert "s01e09" in path


class TestMoviePath:
    def test_basic_path(self):
        movie = MovieMatch(
            tmdb_id=603,
            imdb_id="tt0133093",
            title="The Matrix",
            year=1999,
            runtime_minutes=136,
        )
        path = _movie_path(movie)
        assert path == (
            "Movies/The Matrix (1999) {imdb-tt0133093}/"
            "The Matrix (1999) {imdb-tt0133093}.mkv"
        )

    def test_no_imdb(self):
        movie = MovieMatch(tmdb_id=1, title="Unknown Movie", year=2024)
        path = _movie_path(movie)
        assert path == "Movies/Unknown Movie (2024)/Unknown Movie (2024).mkv"


class TestTvExtraPath:
    def test_featurette_path(self):
        show = TVShowMatch(tmdb_id=4586, tvdb_id=76568, title="Gilmore Girls", year=2000, season_number=1)
        path = _tv_extra_path(show, "behind_the_scenes.mkv")
        assert "Featurettes/behind_the_scenes.mkv" in path
        assert "Gilmore Girls (2000) {tvdb-76568}" in path


# ---------------------------------------------------------------------------
# Disc number parsing
# ---------------------------------------------------------------------------

class TestParseDiscNumber:
    def test_d_format(self):
        assert _parse_disc_number("GILMORE_GIRLS_S1_US_D3") == 3

    def test_disc_format(self):
        assert _parse_disc_number("GILMOREGIRLS_S2_DISC4") == 4

    def test_no_disc(self):
        assert _parse_disc_number("THE_MATRIX") == 1


# ---------------------------------------------------------------------------
# SessionStats
# ---------------------------------------------------------------------------

class TestSessionStats:
    def test_defaults(self):
        stats = SessionStats()
        assert stats.folders_processed == 0
        assert stats.episodes_matched == 0
        assert stats.errors == []
