"""End-to-end tests for the Media Renamer pipeline.

Tests the full flow: scan → classify → match → build paths, using
mocked TMDb data to avoid network calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from media_renamer.config import AppConfig
from media_renamer.identifier import classify_content_type
from media_renamer.matcher import (
    compute_disc_episode_offset,
    match_episodes_by_duration,
    match_movie,
    reclassify_unmatched,
)
from media_renamer.models import (
    ContentType,
    DiscFolder,
    EpisodeInfo,
    EpisodeMatch,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
    TVShowMatch,
)
from media_renamer.renamer import (
    build_movie_dest,
    build_movie_extra_dest,
    build_tv_episode_dest,
    build_tv_extra_dest,
    execute_movie_moves,
    execute_tv_moves,
    sanitize_filename,
    write_processing_log,
)
from media_renamer.scanner import classify_disc_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mf(name: str, dur_min: float, cls: FileClassification = FileClassification.UNKNOWN) -> MediaFile:
    return MediaFile(
        path=Path(f"D:/Video/processed/DISC/{name}"),
        filename=name,
        duration_seconds=dur_min * 60,
        classification=cls,
    )


def _cfg() -> AppConfig:
    return AppConfig()


# Gilmore Girls S1 episode data (from TMDb)
GG_S1_EPISODES = [
    EpisodeInfo(season_number=1, episode_number=i+1, title=t, runtime_minutes=r)
    for i, (t, r) in enumerate([
        ("Pilot", 44), ("The Lorelais' First Day at Chilton", 43),
        ("Kill Me Now", 43), ("The Deer Hunters", 43),
    ])
]


# ---------------------------------------------------------------------------
# E2E: TV disc — scan → classify → match → path
# ---------------------------------------------------------------------------


class TestE2ETvDisc:
    """Full pipeline for a 4-episode TV disc (like Gilmore Girls S1D1)."""

    def _build_disc(self) -> DiscFolder:
        return DiscFolder(
            path=Path("D:/Video/processed/GILMORE_GIRLS_S1_US_D1"),
            name="GILMORE_GIRLS_S1_US_D1",
            files=[
                _mf("GILMORE GIRLS SEASON ONE DISC 1-B1_t01.mkv", 44.2),
                _mf("GILMORE GIRLS SEASON ONE DISC 1-C1_t02.mkv", 43.2),
                _mf("GILMORE GIRLS SEASON ONE DISC 1-D1_t03.mkv", 44.0),
                _mf("GILMORE GIRLS SEASON ONE DISC 1-E1_t04.mkv", 44.5),
                _mf("GILMORE GIRLS SEASON ONE DISC 1-F1_t00.mkv", 175.9),
                _mf("GILMORE GIRLS SEASON ONE DISC 1-G1_t05.mkv", 2.3),
            ],
        )

    def test_classify_detects_play_all_and_bonus(self):
        disc = self._build_disc()
        classified = classify_disc_files(disc, _cfg())

        by_name = {f.filename: f for f in classified.files}
        assert by_name["GILMORE GIRLS SEASON ONE DISC 1-F1_t00.mkv"].classification == FileClassification.PLAY_ALL
        assert by_name["GILMORE GIRLS SEASON ONE DISC 1-G1_t05.mkv"].classification == FileClassification.BONUS

        episodes = [f for f in classified.files if f.classification == FileClassification.EPISODE]
        assert len(episodes) == 4

    def test_content_type_is_tv(self):
        disc = self._build_disc()
        classified = classify_disc_files(disc, _cfg())
        assert classify_content_type(classified, _cfg()) == ContentType.TV_SERIES

    def test_matches_4_episodes(self):
        disc = self._build_disc()
        classified = classify_disc_files(disc, _cfg())
        sorted_files = sorted(classified.files, key=lambda f: f.filename)

        matched, unmatched = match_episodes_by_duration(
            sorted_files, GG_S1_EPISODES, _cfg(), episode_offset=0,
        )
        assert len(matched) == 4
        assert len(unmatched) == 0
        assert matched[0].episode.title == "Pilot"
        assert matched[3].episode.title == "The Deer Hunters"

    def test_plex_paths_correct(self):
        disc = self._build_disc()
        classified = classify_disc_files(disc, _cfg())
        sorted_files = sorted(classified.files, key=lambda f: f.filename)
        matched, _ = match_episodes_by_duration(
            sorted_files, GG_S1_EPISODES, _cfg(), episode_offset=0,
        )

        show = TVShowMatch(
            tmdb_id=4586, tvdb_id=76568, title="Gilmore Girls",
            year=2000, season_number=1,
        )

        dest = Path("D:/staging")
        for em in matched:
            path = build_tv_episode_dest(dest, show, em)
            path_str = str(path)

            # Verify Plex naming components
            assert "TV Shows" in path_str
            assert "Gilmore Girls (2000) {tvdb-76568}" in path_str
            assert "Season 01" in path_str
            assert f"s01e{em.episode.episode_number:02d}" in path_str
            assert em.episode.title in path_str
            assert path_str.endswith(".mkv")

    def test_dry_run_moves_no_files(self):
        disc = self._build_disc()
        classified = classify_disc_files(disc, _cfg())
        sorted_files = sorted(classified.files, key=lambda f: f.filename)
        matched, _ = match_episodes_by_duration(
            sorted_files, GG_S1_EPISODES, _cfg(), episode_offset=0,
        )

        show = TVShowMatch(
            tmdb_id=4586, tvdb_id=76568, title="Gilmore Girls",
            year=2000, season_number=1,
        )

        result = execute_tv_moves(
            Path("D:/staging"), show, matched, [], [], dry_run=True,
        )
        assert result.moved_count == 4
        # Original files should still "exist" (dry run)
        for a in result.file_actions:
            assert "DRY RUN" in a.description


# ---------------------------------------------------------------------------
# E2E: TV disc with edge case (21.9 min file)
# ---------------------------------------------------------------------------


class TestE2ETvDiscEdgeCase:
    """S1D6: only 1 episode remains, plus 21.9 min unmatched file."""

    def test_21min_file_reclassified_as_unknown(self):
        disc = DiscFolder(
            path=Path("D:/Video/processed/GILMORE_GIRLS_S1_US_D6"),
            name="GILMORE_GIRLS_S1_US_D6",
            files=[
                _mf("D6-B1.mkv", 21.9),
                _mf("D6-B2.mkv", 44.4),
                _mf("D6-B3.mkv", 2.3),
                _mf("D6-B4.mkv", 3.6),
                _mf("D6-C1.mkv", 44.8),
            ],
        )
        classified = classify_disc_files(disc, _cfg())
        sorted_files = sorted(classified.files, key=lambda f: f.filename)

        # Only 1 episode at offset 20 (episode 21, runtime 43 min)
        ep21 = [EpisodeInfo(season_number=1, episode_number=21, title="Love, Daisies and Troubadours", runtime_minutes=43)]
        matched, unmatched = match_episodes_by_duration(
            sorted_files, ep21, _cfg(), episode_offset=0,
        )

        # 21.9 min file should NOT match (diff too large)
        assert len(matched) == 1
        matched_names = {m.file.filename for m in matched}
        assert "D6-B1.mkv" not in matched_names

        # Reclassify
        reclassified = reclassify_unmatched(sorted_files, matched_names, _cfg())
        by_name = {f.filename: f for f in reclassified}
        assert by_name["D6-B1.mkv"].classification == FileClassification.UNKNOWN


# ---------------------------------------------------------------------------
# E2E: Movie disc
# ---------------------------------------------------------------------------


class TestE2EMovieDisc:
    """Full pipeline for a movie disc (like The Matrix)."""

    def _build_disc(self) -> DiscFolder:
        return DiscFolder(
            path=Path("D:/Video/processed/THE_MATRIX"),
            name="THE_MATRIX",
            files=[
                _mf("THE_MATRIX-B1_t00.mkv", 136.5),
                _mf("THE_MATRIX-C1_t01.mkv", 5.3),
                _mf("THE_MATRIX-D1_t02.mkv", 3.1),
                _mf("THE_MATRIX-E1_t03.mkv", 2.7),
            ],
        )

    def test_content_type_is_movie(self):
        disc = self._build_disc()
        classified = classify_disc_files(disc, _cfg())
        # Only 1 episode-length file → MOVIE
        assert classify_content_type(classified, _cfg()) == ContentType.MOVIE

    def test_longest_file_matches_movie(self):
        disc = self._build_disc()
        classified = classify_disc_files(disc, _cfg())
        sorted_files = sorted(classified.files, key=lambda f: f.filename)

        movie = MovieMatch(
            tmdb_id=603, imdb_id="tt0133093",
            title="The Matrix", year=1999, runtime_minutes=136,
        )
        main_file, confidence, extras = match_movie(sorted_files, movie, _cfg())

        assert main_file is not None
        assert main_file.duration_seconds == pytest.approx(136.5 * 60)
        assert confidence == MatchConfidence.HIGH

    def test_movie_plex_path(self):
        movie = MovieMatch(
            tmdb_id=603, imdb_id="tt0133093",
            title="The Matrix", year=1999, runtime_minutes=136,
        )
        path = build_movie_dest(Path("D:/staging"), movie)
        path_str = str(path)

        assert "Movies" in path_str
        assert "The Matrix (1999) {imdb-tt0133093}" in path_str
        assert path_str.endswith(".mkv")

    def test_movie_extra_plex_path(self):
        movie = MovieMatch(
            tmdb_id=603, imdb_id="tt0133093",
            title="The Matrix", year=1999, runtime_minutes=136,
        )
        extra = _mf("bonus.mkv", 5.0, FileClassification.BONUS)
        path = build_movie_extra_dest(Path("D:/staging"), movie, extra)
        path_str = str(path)

        assert "Movies" in path_str
        assert "The Matrix (1999)" in path_str
        assert "featurette-1" in path_str


# ---------------------------------------------------------------------------
# E2E: Sequential disc mapping
# ---------------------------------------------------------------------------


class TestE2ESequentialDiscMapping:
    """Verify episode offsets work across a multi-disc set."""

    def test_6_disc_21_episode_offsets(self):
        """S1: 21 eps across 6 discs (4+4+4+4+4+1)."""
        total = 21
        offsets = [compute_disc_episode_offset(d, 4, total) for d in range(1, 7)]
        assert offsets == [0, 4, 8, 12, 16, 20]

    def test_6_disc_22_episode_offsets(self):
        """S2: 22 eps across 6 discs (4+4+4+4+4+2)."""
        total = 22
        offsets = [compute_disc_episode_offset(d, 4, total) for d in range(1, 7)]
        assert offsets == [0, 4, 8, 12, 16, 20]


# ---------------------------------------------------------------------------
# E2E: Special characters in titles
# ---------------------------------------------------------------------------


class TestE2ESpecialCharacters:
    def test_sanitize_colon_in_title(self):
        """Titles with colons should be sanitized for Windows paths."""
        movie = MovieMatch(
            tmdb_id=1, imdb_id="tt0000001",
            title='Star Wars: The Force Awakens', year=2015,
        )
        path = build_movie_dest(Path("D:/staging"), movie)
        # Colon in title removed (ignore drive letter colon)
        path_no_drive = str(path)[2:]  # strip "D:"
        assert ":" not in path_no_drive
        assert "Star Wars The Force Awakens" in str(path)

    def test_question_mark_in_episode_title(self):
        show = TVShowMatch(tmdb_id=1, tvdb_id=1, title="Show", year=2020, season_number=1)
        em = EpisodeMatch(
            file=_mf("test.mkv", 44.0),
            episode=EpisodeInfo(season_number=1, episode_number=1, title="Who Did It?"),
            confidence=MatchConfidence.HIGH,
        )
        path = build_tv_episode_dest(Path("D:/staging"), show, em)
        assert "?" not in str(path)
        assert "Who Did It" in str(path)


# ---------------------------------------------------------------------------
# E2E: Processing log
# ---------------------------------------------------------------------------


class TestE2EProcessingLog:
    def test_full_log_cycle(self, tmp_path: Path):
        """Process a disc, write log, verify log contents."""
        show = TVShowMatch(
            tmdb_id=4586, tvdb_id=76568, title="Gilmore Girls",
            year=2000, season_number=1,
        )
        ep = EpisodeInfo(season_number=1, episode_number=1, title="Pilot", runtime_minutes=44)
        em = EpisodeMatch(
            file=_mf("ep01.mkv", 44.2),
            episode=ep, confidence=MatchConfidence.HIGH,
        )

        result = execute_tv_moves(
            tmp_path, show, [em], [], [], dry_run=True,
        )
        log_path = write_processing_log(tmp_path, [result], dry_run=False)

        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert data[0]["total_moved"] == 1
        assert data[0]["results"][0]["matched_title"] == "Gilmore Girls"


# ---------------------------------------------------------------------------
# E2E: Empty and edge-case inputs
# ---------------------------------------------------------------------------


class TestE2EEdgeCases:
    def test_empty_disc_folder(self):
        disc = DiscFolder(
            path=Path("D:/Video/processed/EMPTY"),
            name="EMPTY",
            files=[],
        )
        classified = classify_disc_files(disc, _cfg())
        assert len(classified.files) == 0
        assert classify_content_type(classified, _cfg()) == ContentType.UNKNOWN

    def test_all_bonus_disc(self):
        disc = DiscFolder(
            path=Path("D:/Video/processed/BONUS_ONLY"),
            name="BONUS_ONLY",
            files=[
                _mf("bonus1.mkv", 3.0),
                _mf("bonus2.mkv", 5.0),
                _mf("bonus3.mkv", 2.0),
            ],
        )
        classified = classify_disc_files(disc, _cfg())
        all_bonus = all(f.classification == FileClassification.BONUS for f in classified.files)
        assert all_bonus
        assert classify_content_type(classified, _cfg()) == ContentType.UNKNOWN

    def test_no_episodes_to_match(self):
        """Matching with empty episode list returns all files as unmatched."""
        files = [_mf("ep1.mkv", 44.0, FileClassification.EPISODE)]
        matched, unmatched = match_episodes_by_duration(files, [], _cfg())
        assert len(matched) == 0
        assert len(unmatched) == 1

    def test_config_with_bad_yaml_values(self):
        """Config with non-numeric values should use defaults."""
        from media_renamer.config import _safe_float
        assert _safe_float("not_a_number", 3.0) == 3.0
        assert _safe_float(None, 5.0) == 5.0
        assert _safe_float("2.5", 3.0) == 2.5

    def test_sanitize_empty_string(self):
        assert sanitize_filename("") == "untitled"
        assert sanitize_filename("   ") == "untitled"
        assert sanitize_filename("...") == "untitled"
