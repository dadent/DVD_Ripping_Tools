"""Tests for media_renamer.models — Pydantic data models."""

from pathlib import Path

import pytest

from media_renamer.models import (
    ActionTaken,
    ContentType,
    DiscFolder,
    EpisodeInfo,
    EpisodeMatch,
    FileAction,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
    ProcessingResult,
    TVShowMatch,
)


# ---------------------------------------------------------------------------
# MediaFile
# ---------------------------------------------------------------------------


class TestMediaFile:
    def test_basic_creation(self):
        mf = MediaFile(
            path=Path("D:/rips/MOVIE/movie_t00.mkv"),
            filename="movie_t00.mkv",
            duration_seconds=8100.0,
        )
        assert mf.filename == "movie_t00.mkv"
        assert mf.duration_seconds == 8100.0
        assert mf.classification == FileClassification.UNKNOWN

    def test_duration_minutes(self):
        mf = MediaFile(
            path=Path("x.mkv"), filename="x.mkv", duration_seconds=2700.0
        )
        assert mf.duration_minutes == 45.0

    def test_optional_metadata_defaults(self):
        mf = MediaFile(
            path=Path("x.mkv"), filename="x.mkv", duration_seconds=100.0
        )
        assert mf.audio_track_count == 0
        assert mf.audio_languages == []
        assert mf.subtitle_track_count == 0
        assert mf.subtitle_languages == []
        assert mf.video_resolution is None
        assert mf.chapter_count == 0
        assert mf.chapter_names == []
        assert mf.file_size_bytes == 0

    def test_full_metadata(self):
        mf = MediaFile(
            path=Path("x.mkv"),
            filename="x.mkv",
            duration_seconds=2640.0,
            audio_track_count=2,
            audio_languages=["eng", "spa"],
            subtitle_track_count=3,
            subtitle_languages=["eng", "spa", "fre"],
            video_resolution="1920x1080",
            chapter_count=12,
            chapter_names=["Chapter 1", "Chapter 2"],
            file_size_bytes=1_500_000_000,
            classification=FileClassification.EPISODE,
        )
        assert mf.audio_track_count == 2
        assert mf.video_resolution == "1920x1080"
        assert mf.classification == FileClassification.EPISODE
        assert mf.duration_minutes == 44.0


# ---------------------------------------------------------------------------
# DiscFolder
# ---------------------------------------------------------------------------


class TestDiscFolder:
    def test_empty_folder(self):
        df = DiscFolder(path=Path("D:/rips/FRIENDS_S2_D3"), name="FRIENDS_S2_D3")
        assert df.content_type == ContentType.UNKNOWN
        assert df.files == []
        assert df.parsed_title is None

    def test_folder_with_files(self):
        files = [
            MediaFile(path=Path("a.mkv"), filename="a.mkv", duration_seconds=1320.0),
            MediaFile(path=Path("b.mkv"), filename="b.mkv", duration_seconds=1350.0),
        ]
        df = DiscFolder(
            path=Path("D:/rips/FRIENDS_S2_D3"),
            name="FRIENDS_S2_D3",
            files=files,
            content_type=ContentType.TV_SERIES,
            parsed_title="Friends",
            parsed_season=2,
            parsed_disc=3,
        )
        assert len(df.files) == 2
        assert df.content_type == ContentType.TV_SERIES
        assert df.parsed_season == 2


# ---------------------------------------------------------------------------
# MovieMatch / TVShowMatch
# ---------------------------------------------------------------------------


class TestMovieMatch:
    def test_basic(self):
        mm = MovieMatch(tmdb_id=603, title="The Matrix", year=1999, imdb_id="tt0133093")
        assert mm.tmdb_id == 603
        assert mm.confidence == MatchConfidence.MEDIUM

    def test_high_confidence(self):
        mm = MovieMatch(
            tmdb_id=603,
            title="The Matrix",
            confidence=MatchConfidence.HIGH,
        )
        assert mm.confidence == MatchConfidence.HIGH


class TestTVShowMatch:
    def test_with_episodes(self):
        ep = EpisodeMatch(
            file=MediaFile(
                path=Path("t01.mkv"), filename="t01.mkv", duration_seconds=2652.0
            ),
            episode=EpisodeInfo(
                season_number=1, episode_number=1, title="Pilot", runtime_minutes=44
            ),
            confidence=MatchConfidence.HIGH,
            duration_diff_minutes=0.2,
        )
        tv = TVShowMatch(
            tmdb_id=1668,
            tvdb_id=79168,
            title="Friends",
            year=1994,
            season_number=2,
            episode_matches=[ep],
        )
        assert tv.tvdb_id == 79168
        assert len(tv.episode_matches) == 1
        assert tv.episode_matches[0].duration_diff_minutes == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# ProcessingResult
# ---------------------------------------------------------------------------


class TestProcessingResult:
    def test_counts(self):
        result = ProcessingResult(
            folder_name="TEST",
            content_type=ContentType.MOVIE,
            file_actions=[
                FileAction(
                    source_path=Path("a.mkv"),
                    dest_path=Path("b.mkv"),
                    action=ActionTaken.MOVED,
                ),
                FileAction(
                    source_path=Path("c.mkv"),
                    action=ActionTaken.SKIPPED,
                    description="Play All track",
                ),
                FileAction(
                    source_path=Path("d.mkv"),
                    action=ActionTaken.ERROR,
                    description="Permission denied",
                ),
            ],
        )
        assert result.moved_count == 1
        assert result.skipped_count == 1
        assert result.error_count == 1

    def test_empty_result(self):
        result = ProcessingResult(
            folder_name="EMPTY", content_type=ContentType.UNKNOWN
        )
        assert result.moved_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_content_type_values(self):
        assert ContentType.MOVIE.value == "movie"
        assert ContentType.TV_SERIES.value == "tv_series"
        assert ContentType.UNKNOWN.value == "unknown"

    def test_file_classification_values(self):
        assert FileClassification.PLAY_ALL.value == "play_all"
        assert FileClassification.BONUS.value == "bonus"
        assert FileClassification.MAIN_FEATURE.value == "main_feature"
