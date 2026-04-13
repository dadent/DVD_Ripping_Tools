"""Tests for media_renamer.matcher — duration matching and movie identification."""

from __future__ import annotations

from pathlib import Path

import pytest

from media_renamer.config import AppConfig
from media_renamer.matcher import (
    compute_disc_episode_offset,
    estimate_episodes_per_disc,
    match_episodes_by_duration,
    match_movie,
    reclassify_unmatched,
    _score_confidence,
)
from media_renamer.models import (
    EpisodeInfo,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mf(name: str, dur_min: float, cls: FileClassification = FileClassification.EPISODE) -> MediaFile:
    return MediaFile(
        path=Path(f"/fake/{name}"),
        filename=name,
        duration_seconds=dur_min * 60,
        classification=cls,
    )


def _ep(num: int, title: str, runtime: int | None = None, season: int = 1) -> EpisodeInfo:
    return EpisodeInfo(
        season_number=season,
        episode_number=num,
        title=title,
        runtime_minutes=runtime,
    )


def _cfg(**overrides) -> AppConfig:
    return AppConfig(**overrides)


# Gilmore Girls S1 episode runtimes (from TMDb)
GG_S1_EPISODES = [
    _ep(1, "Pilot", 44),
    _ep(2, "The Lorelais' First Day at Chilton", 43),
    _ep(3, "Kill Me Now", 43),
    _ep(4, "The Deer Hunters", 43),
    _ep(5, "Cinnamon's Wake", 42),
    _ep(6, "Rory's Birthday Parties", 44),
    _ep(7, "Kiss and Tell", 44),
    _ep(8, "Love and War and Snow", 44),
    _ep(9, "Rory's Dance", 44),
    _ep(10, "Forgiveness and Stuff", 42),
    _ep(11, "Paris is Burning", 44),
    _ep(12, "Double Date", 42),
    _ep(13, "Concert Interruptus", 39),
    _ep(14, "That Damn Donna Reed", 44),
    _ep(15, "Christopher Returns", 43),
    _ep(16, "Star-Crossed Lovers and Other Strangers", 44),
    _ep(17, "The Breakup, Part 2", 44),
    _ep(18, "The Third Lorelai", 44),
    _ep(19, "Emily in Wonderland", 42),
    _ep(20, "P.S. I Lo...", 43),
    _ep(21, "Love, Daisies and Troubadours", 43),
]


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------


class TestConfidenceScoring:
    def test_high_confidence(self):
        assert _score_confidence(0.2, 3.0) == MatchConfidence.HIGH

    def test_medium_confidence(self):
        assert _score_confidence(1.5, 3.0) == MatchConfidence.MEDIUM

    def test_low_confidence(self):
        assert _score_confidence(2.5, 3.0) == MatchConfidence.LOW

    def test_exact_match(self):
        assert _score_confidence(0.0, 3.0) == MatchConfidence.HIGH


# ---------------------------------------------------------------------------
# Disc episode offset
# ---------------------------------------------------------------------------


class TestDiscEpisodeOffset:
    def test_disc_1(self):
        assert compute_disc_episode_offset(1, 4, 21) == 0

    def test_disc_2(self):
        assert compute_disc_episode_offset(2, 4, 21) == 4

    def test_disc_3(self):
        assert compute_disc_episode_offset(3, 4, 21) == 8

    def test_disc_6_capped(self):
        # Disc 6 starts at episode 20, but there are only 21 episodes
        assert compute_disc_episode_offset(6, 4, 21) == 20

    def test_disc_beyond_total(self):
        assert compute_disc_episode_offset(7, 4, 21) == 21

    def test_estimate_eps_per_disc(self):
        assert estimate_episodes_per_disc(21, 6) == 4
        assert estimate_episodes_per_disc(22, 6) == 4
        assert estimate_episodes_per_disc(24, 6) == 4
        assert estimate_episodes_per_disc(25, 6) == 5


# ---------------------------------------------------------------------------
# Episode matching — S1 Disc 1 (4 episodes)
# ---------------------------------------------------------------------------


class TestMatchEpisodesDisc1:
    def test_matches_4_episodes(self):
        """S1D1: 4 episode files at ~44 min each → episodes 1-4."""
        files = [
            _mf("D1-B1_t01.mkv", 44.2),
            _mf("D1-C1_t02.mkv", 43.2),
            _mf("D1-D1_t03.mkv", 44.0),
            _mf("D1-E1_t04.mkv", 44.5),
            _mf("D1-F1_t00.mkv", 175.9, FileClassification.PLAY_ALL),
        ]
        matched, unmatched = match_episodes_by_duration(
            files, GG_S1_EPISODES, _cfg(), episode_offset=0
        )

        assert len(matched) == 4
        assert len(unmatched) == 0

        # Check episode assignments
        assert matched[0].episode.episode_number == 1
        assert matched[0].episode.title == "Pilot"
        assert matched[1].episode.episode_number == 2
        assert matched[2].episode.episode_number == 3
        assert matched[3].episode.episode_number == 4

    def test_high_confidence_for_close_matches(self):
        """All S1D1 matches should be HIGH confidence (diff < 0.75 min)."""
        files = [
            _mf("D1-B1.mkv", 44.2),  # TMDb: 44 → diff 0.2
            _mf("D1-C1.mkv", 43.2),  # TMDb: 43 → diff 0.2
            _mf("D1-D1.mkv", 44.0),  # TMDb: 43 → diff 1.0
            _mf("D1-E1.mkv", 44.5),  # TMDb: 43 → diff 1.5
        ]
        matched, _ = match_episodes_by_duration(
            files, GG_S1_EPISODES, _cfg(), episode_offset=0
        )

        assert matched[0].confidence == MatchConfidence.HIGH  # 0.2 min
        assert matched[1].confidence == MatchConfidence.HIGH  # 0.2 min


# ---------------------------------------------------------------------------
# Episode matching — S1 Disc 2 (offset = 4)
# ---------------------------------------------------------------------------


class TestMatchEpisodesDisc2:
    def test_matches_with_offset(self):
        """S1D2: 4 files → episodes 5-8 (offset=4)."""
        files = [
            _mf("D2-C1.mkv", 43.0),
            _mf("D2-D1.mkv", 44.5),
            _mf("D2-E1.mkv", 44.5),
            _mf("D2-F1.mkv", 44.5),
        ]
        matched, unmatched = match_episodes_by_duration(
            files, GG_S1_EPISODES, _cfg(), episode_offset=4
        )

        assert len(matched) == 4
        assert matched[0].episode.episode_number == 5
        assert matched[0].episode.title == "Cinnamon's Wake"
        assert matched[3].episode.episode_number == 8


# ---------------------------------------------------------------------------
# Episode matching — S1 Disc 6 (edge case: 21.9 min file)
# ---------------------------------------------------------------------------


class TestMatchEpisodesDisc6EdgeCase:
    def test_21min_file_doesnt_match(self):
        """S1D6: 21.9 min file should NOT match any ~42-44 min episode."""
        files = [
            _mf("D6-B1.mkv", 21.9),   # ambiguous — not an episode
            _mf("D6-B2.mkv", 44.4),   # episode
            _mf("D6-C1.mkv", 44.8),   # episode
            _mf("D6-B3.mkv", 2.3, FileClassification.BONUS),
            _mf("D6-B4.mkv", 3.6, FileClassification.BONUS),
        ]
        # Disc 6 of S1: episode offset = 20 (5 discs × 4 eps = 20)
        # Only episode 21 remains
        matched, unmatched = match_episodes_by_duration(
            files, GG_S1_EPISODES, _cfg(), episode_offset=20
        )

        # 21.9 min doesn't match episode 21 (43 min) — diff is 21.1 min > 3 min tolerance
        # Only 44.4 should match episode 21
        assert len(matched) == 1
        assert matched[0].episode.episode_number == 21
        assert matched[0].file.filename == "D6-B1.mkv" or matched[0].file.filename == "D6-B2.mkv"
        # The 21.9 min file should be unmatched
        unmatched_names = {f.filename for f in unmatched}
        assert "D6-B1.mkv" in unmatched_names


# ---------------------------------------------------------------------------
# Episode matching — S2 Disc 6 (2 episodes + bonus)
# ---------------------------------------------------------------------------


class TestMatchEpisodes2EpDisc:
    def test_matches_2_episodes(self):
        """A disc with only 2 episode-length files should match correctly."""
        s2_eps = [
            _ep(1, "Ep1", 44, season=2),
            _ep(2, "Ep2", 45, season=2),
        ]
        files = [
            _mf("D6-B1.mkv", 43.8),
            _mf("D6-C1.mkv", 44.9),
            _mf("D6-D4.mkv", 5.4, FileClassification.BONUS),
        ]
        matched, unmatched = match_episodes_by_duration(
            files, s2_eps, _cfg(), episode_offset=0
        )

        assert len(matched) == 2
        assert len(unmatched) == 0
        assert matched[0].episode.episode_number == 1
        assert matched[1].episode.episode_number == 2


# ---------------------------------------------------------------------------
# Movie matching
# ---------------------------------------------------------------------------


class TestMatchMovie:
    def test_matches_main_feature(self):
        movie = MovieMatch(tmdb_id=603, title="The Matrix", year=1999, runtime_minutes=136, imdb_id="tt0133093")
        files = [
            _mf("main.mkv", 136.5, FileClassification.EPISODE),
            _mf("bonus1.mkv", 5.0, FileClassification.BONUS),
            _mf("bonus2.mkv", 3.0, FileClassification.BONUS),
        ]
        main, confidence, extras = match_movie(files, movie, _cfg())

        assert main is not None
        assert main.filename == "main.mkv"
        assert confidence == MatchConfidence.HIGH
        assert len(extras) == 2

    def test_low_confidence_for_duration_mismatch(self):
        movie = MovieMatch(tmdb_id=603, title="The Matrix", runtime_minutes=136)
        files = [
            _mf("main.mkv", 150.0, FileClassification.EPISODE),
        ]
        main, confidence, extras = match_movie(files, movie, _cfg())

        assert main is not None
        assert confidence == MatchConfidence.LOW

    def test_no_candidates(self):
        movie = MovieMatch(tmdb_id=603, title="The Matrix", runtime_minutes=136)
        files = [
            _mf("bonus.mkv", 5.0, FileClassification.BONUS),
        ]
        main, confidence, extras = match_movie(files, movie, _cfg())
        assert main is None


# ---------------------------------------------------------------------------
# Reclassification
# ---------------------------------------------------------------------------


class TestReclassifyUnmatched:
    def test_unmatched_episode_becomes_unknown(self):
        """A file classified as EPISODE that didn't match any episode → UNKNOWN."""
        files = [
            _mf("ep1.mkv", 44.0),
            _mf("ambiguous.mkv", 21.9),
            _mf("bonus.mkv", 3.0, FileClassification.BONUS),
        ]
        matched_names = {"ep1.mkv"}
        result = reclassify_unmatched(files, matched_names, _cfg())

        by_name = {f.filename: f for f in result}
        assert by_name["ep1.mkv"].classification == FileClassification.EPISODE
        assert by_name["ambiguous.mkv"].classification == FileClassification.UNKNOWN
        assert by_name["bonus.mkv"].classification == FileClassification.BONUS

    def test_short_unmatched_becomes_bonus(self):
        """An EPISODE-classified file under bonus threshold → BONUS."""
        files = [
            _mf("short.mkv", 7.0),
        ]
        result = reclassify_unmatched(files, set(), _cfg())
        assert result[0].classification == FileClassification.BONUS


# ---------------------------------------------------------------------------
# Skips non-episode files
# ---------------------------------------------------------------------------


class TestSkipsNonEpisodeFiles:
    def test_play_all_skipped(self):
        """PLAY_ALL files should not be matched."""
        files = [
            _mf("ep1.mkv", 44.0),
            _mf("playall.mkv", 176.0, FileClassification.PLAY_ALL),
        ]
        matched, unmatched = match_episodes_by_duration(
            files, [_ep(1, "Pilot", 44)], _cfg()
        )
        assert len(matched) == 1
        assert matched[0].file.filename == "ep1.mkv"

    def test_bonus_skipped(self):
        """BONUS files should not be matched."""
        files = [
            _mf("ep1.mkv", 44.0),
            _mf("trailer.mkv", 2.0, FileClassification.BONUS),
        ]
        matched, unmatched = match_episodes_by_duration(
            files, [_ep(1, "Pilot", 44)], _cfg()
        )
        assert len(matched) == 1
