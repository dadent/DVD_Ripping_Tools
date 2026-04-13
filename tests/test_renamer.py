"""Tests for media_renamer.renamer — file operations and Plex path construction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from media_renamer.models import (
    ActionTaken,
    ContentType,
    EpisodeInfo,
    EpisodeMatch,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
    ProcessingResult,
    TVShowMatch,
)
from media_renamer.renamer import (
    build_movie_dest,
    build_movie_extra_dest,
    build_tv_episode_dest,
    build_tv_extra_dest,
    execute_movie_moves,
    execute_tv_moves,
    move_file,
    sanitize_filename,
    write_processing_log,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mf(name: str, dur_min: float = 44.0, cls: FileClassification = FileClassification.EPISODE, path: Path | None = None) -> MediaFile:
    p = path or Path(f"D:/Video/processed/DISC1/{name}")
    return MediaFile(
        path=p,
        filename=name,
        duration_seconds=dur_min * 60,
        classification=cls,
    )


def _ep_match(season: int, ep_num: int, title: str, filename: str = "file.mkv") -> EpisodeMatch:
    return EpisodeMatch(
        file=_mf(filename),
        episode=EpisodeInfo(season_number=season, episode_number=ep_num, title=title),
        confidence=MatchConfidence.HIGH,
    )


def _show() -> TVShowMatch:
    return TVShowMatch(
        tmdb_id=4586,
        tvdb_id=76568,
        title="Gilmore Girls",
        year=2000,
        season_number=1,
    )


def _movie() -> MovieMatch:
    return MovieMatch(
        tmdb_id=603,
        imdb_id="tt0133093",
        title="The Matrix",
        year=1999,
        runtime_minutes=136,
    )


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    def test_removes_illegal_chars(self):
        assert sanitize_filename('Movie: The "Sequel"') == "Movie The Sequel"

    def test_removes_slashes(self):
        assert sanitize_filename("A/B\\C") == "ABC"

    def test_removes_pipes_and_questions(self):
        assert sanitize_filename("What? Why|How") == "What WhyHow"

    def test_strips_dots_and_spaces(self):
        assert sanitize_filename("  ..name..  ") == "name"

    def test_empty_becomes_untitled(self):
        assert sanitize_filename("") == "untitled"

    def test_normal_names_unchanged(self):
        assert sanitize_filename("Gilmore Girls (2000) {tvdb-76568}") == "Gilmore Girls (2000) {tvdb-76568}"


# ---------------------------------------------------------------------------
# TV episode path construction
# ---------------------------------------------------------------------------

class TestBuildTvEpisodeDest:
    def test_standard_path(self):
        dest = Path("D:/staging")
        show = _show()
        em = _ep_match(1, 1, "Pilot", "ep01.mkv")
        result = build_tv_episode_dest(dest, show, em)

        assert result == Path(
            "D:/staging/TV Shows/Gilmore Girls (2000) {tvdb-76568}/"
            "Season 01/Gilmore Girls (2000) - s01e01 - Pilot.mkv"
        )

    def test_preserves_extension(self):
        em = _ep_match(2, 5, "Test")
        em = em.model_copy(update={
            "file": _mf("test.mp4", path=Path("D:/Video/test.mp4"))
        })
        result = build_tv_episode_dest(Path("/out"), _show(), em)
        assert result.suffix == ".mp4"

    def test_no_tvdb(self):
        show = TVShowMatch(tmdb_id=1, title="NoTVDB", season_number=1)
        em = _ep_match(1, 1, "Ep1")
        result = build_tv_episode_dest(Path("/out"), show, em)
        assert "tvdb" not in str(result)
        assert "NoTVDB" in str(result)

    def test_two_digit_padding(self):
        em = _ep_match(1, 9, "Nine")
        result = build_tv_episode_dest(Path("/out"), _show(), em)
        assert "s01e09" in str(result)


# ---------------------------------------------------------------------------
# TV extra path construction
# ---------------------------------------------------------------------------

class TestBuildTvExtraDest:
    def test_featurettes_folder(self):
        result = build_tv_extra_dest(Path("/out"), _show(), _mf("bonus.mkv"))
        assert "Featurettes" in str(result)
        assert str(result).endswith("bonus.mkv")


# ---------------------------------------------------------------------------
# Movie path construction
# ---------------------------------------------------------------------------

class TestBuildMovieDest:
    def test_standard_path(self):
        result = build_movie_dest(Path("D:/staging"), _movie())
        assert result == Path(
            "D:/staging/Movies/The Matrix (1999) {imdb-tt0133093}/"
            "The Matrix (1999) {imdb-tt0133093}.mkv"
        )

    def test_no_imdb(self):
        movie = MovieMatch(tmdb_id=1, title="Unknown", year=2024)
        result = build_movie_dest(Path("/out"), movie)
        assert "imdb" not in str(result)
        assert "Unknown (2024)" in str(result)


class TestBuildMovieExtraDest:
    def test_extra_path(self):
        result = build_movie_extra_dest(
            Path("/out"), _movie(), _mf("bonus.mkv"), extra_type="featurette", index=1,
        )
        assert "The Matrix (1999) - featurette-1.mkv" in str(result)

    def test_behind_the_scenes(self):
        result = build_movie_extra_dest(
            Path("/out"), _movie(), _mf("bts.mkv"), extra_type="behindthescenes", index=2,
        )
        assert "behindthescenes-2" in str(result)


# ---------------------------------------------------------------------------
# move_file — dry run
# ---------------------------------------------------------------------------

class TestMoveFileDryRun:
    def test_dry_run_returns_moved_action(self):
        src = Path("D:/src/file.mkv")
        dst = Path("D:/dst/file.mkv")
        action = move_file(src, dst, dry_run=True)

        assert action.action == ActionTaken.MOVED
        assert action.source_path == src
        assert action.dest_path == dst
        assert "DRY RUN" in action.description


# ---------------------------------------------------------------------------
# move_file — actual move (using tmp dir)
# ---------------------------------------------------------------------------

class TestMoveFileReal:
    def test_moves_file(self, tmp_path: Path):
        src = tmp_path / "source" / "test.mkv"
        src.parent.mkdir()
        src.write_text("test content")

        dst = tmp_path / "dest" / "sub" / "test.mkv"
        action = move_file(src, dst, dry_run=False)

        assert action.action == ActionTaken.MOVED
        assert dst.exists()
        assert not src.exists()
        assert dst.read_text() == "test content"

    def test_creates_parent_dirs(self, tmp_path: Path):
        src = tmp_path / "test.mkv"
        src.write_text("content")

        dst = tmp_path / "a" / "b" / "c" / "test.mkv"
        action = move_file(src, dst, dry_run=False)

        assert action.action == ActionTaken.MOVED
        assert dst.exists()

    def test_error_on_missing_source(self, tmp_path: Path):
        src = tmp_path / "nonexistent.mkv"
        dst = tmp_path / "dest.mkv"
        action = move_file(src, dst, dry_run=False)

        assert action.action == ActionTaken.ERROR
        assert "failed" in action.description.lower()


# ---------------------------------------------------------------------------
# execute_tv_moves — dry run
# ---------------------------------------------------------------------------

class TestExecuteTvMoves:
    def test_dry_run_records_actions(self):
        show = _show()
        matched = [_ep_match(1, 1, "Pilot", "ep01.mkv")]
        extras = [_mf("bonus.mkv", 3.0, FileClassification.BONUS)]
        skipped = [_mf("playall.mkv", 176.0, FileClassification.PLAY_ALL)]

        result = execute_tv_moves(
            Path("/staging"), show, matched, extras, skipped, dry_run=True,
        )

        assert result.content_type == ContentType.TV_SERIES
        assert result.moved_count == 2  # episode + extra
        assert result.skipped_count == 1  # play_all


# ---------------------------------------------------------------------------
# execute_movie_moves — dry run
# ---------------------------------------------------------------------------

class TestExecuteMovieMoves:
    def test_dry_run_records_actions(self):
        movie = _movie()
        main = _mf("main.mkv", 136.0, FileClassification.EPISODE)
        extras = [
            _mf("bonus.mkv", 5.0, FileClassification.BONUS),
            _mf("playall.mkv", 140.0, FileClassification.PLAY_ALL),
        ]

        result = execute_movie_moves(
            Path("/staging"), movie, main, extras, dry_run=True,
        )

        assert result.content_type == ContentType.MOVIE
        assert result.moved_count == 2  # main + bonus
        assert result.skipped_count == 1  # play_all


# ---------------------------------------------------------------------------
# Processing log
# ---------------------------------------------------------------------------

class TestWriteProcessingLog:
    def test_dry_run_doesnt_write(self, tmp_path: Path):
        result = ProcessingResult(
            folder_name="test",
            content_type=ContentType.TV_SERIES,
        )
        log_path = write_processing_log(tmp_path, [result], dry_run=True)
        assert not log_path.exists()

    def test_writes_json_log(self, tmp_path: Path):
        result = ProcessingResult(
            folder_name="GILMORE_GIRLS_S1_D1",
            content_type=ContentType.TV_SERIES,
            matched_title="Gilmore Girls",
        )
        log_path = write_processing_log(tmp_path, [result], dry_run=False)

        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["folders_processed"] == 1
        assert data[0]["results"][0]["folder"] == "GILMORE_GIRLS_S1_D1"

    def test_appends_to_existing_log(self, tmp_path: Path):
        r1 = ProcessingResult(folder_name="disc1", content_type=ContentType.TV_SERIES)
        write_processing_log(tmp_path, [r1], dry_run=False)

        r2 = ProcessingResult(folder_name="disc2", content_type=ContentType.MOVIE)
        write_processing_log(tmp_path, [r2], dry_run=False)

        data = json.loads((tmp_path / "media_renamer.log").read_text())
        assert len(data) == 2  # two log sessions
