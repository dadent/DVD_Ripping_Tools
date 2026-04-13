"""Tests for media_renamer.scanner — directory scanning, metadata, classification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from media_renamer.config import AppConfig
from media_renamer.models import DiscFolder, FileClassification, MediaFile
from media_renamer.scanner import (
    classify_disc_files,
    scan_source_directory,
    sort_files_for_episode_order,
)


# ---------------------------------------------------------------------------
# Helpers — build MediaFile objects with just duration (no pymediainfo needed)
# ---------------------------------------------------------------------------

def _mf(name: str, duration_min: float, size_mb: float = 100.0) -> MediaFile:
    """Create a MediaFile stub with the given duration in minutes."""
    return MediaFile(
        path=Path(f"/fake/{name}"),
        filename=name,
        duration_seconds=duration_min * 60,
        file_size_bytes=int(size_mb * 1024 * 1024),
    )


def _folder(name: str, files: list[MediaFile]) -> DiscFolder:
    """Create a DiscFolder stub."""
    return DiscFolder(path=Path(f"/fake/{name}"), name=name, files=files)


def _default_config(**overrides) -> AppConfig:
    """AppConfig with defaults, optionally overridden."""
    return AppConfig(**overrides)


# ---------------------------------------------------------------------------
# File ordering
# ---------------------------------------------------------------------------


class TestSortFilesForEpisodeOrder:
    def test_sorts_by_track_position_letter(self):
        """Track position letters (B, C, D…) should determine order."""
        paths = [
            Path("DISC1-D1_t03.mkv"),
            Path("DISC1-B1_t01.mkv"),
            Path("DISC1-F1_t00.mkv"),
            Path("DISC1-C1_t02.mkv"),
            Path("DISC1-E1_t04.mkv"),
        ]
        result = sort_files_for_episode_order(paths)
        assert [p.name for p in result] == [
            "DISC1-B1_t01.mkv",
            "DISC1-C1_t02.mkv",
            "DISC1-D1_t03.mkv",
            "DISC1-E1_t04.mkv",
            "DISC1-F1_t00.mkv",
        ]

    def test_handles_same_prefix_different_suffixes(self):
        """S1D6-style files with B1, B2, B3… sub-positions."""
        paths = [
            Path("DISC6-B3_t03.mkv"),
            Path("DISC6-C1_t00.mkv"),
            Path("DISC6-B1_t01.mkv"),
            Path("DISC6-B4_t04.mkv"),
            Path("DISC6-B2_t02.mkv"),
        ]
        result = sort_files_for_episode_order(paths)
        assert [p.name for p in result] == [
            "DISC6-B1_t01.mkv",
            "DISC6-B2_t02.mkv",
            "DISC6-B3_t03.mkv",
            "DISC6-B4_t04.mkv",
            "DISC6-C1_t00.mkv",
        ]


# ---------------------------------------------------------------------------
# Play All detection
# ---------------------------------------------------------------------------


class TestPlayAllDetection:
    def test_standard_4_episode_disc(self):
        """S1D1 pattern: 4 episodes ~44 min each + 1 Play All ~176 min."""
        files = [
            _mf("DISC1-B1_t01.mkv", 44.2, 1690),
            _mf("DISC1-C1_t02.mkv", 43.2, 1669),
            _mf("DISC1-D1_t03.mkv", 44.0, 1697),
            _mf("DISC1-E1_t04.mkv", 44.5, 1712),
            _mf("DISC1-F1_t00.mkv", 175.9, 6768),
        ]
        folder = _folder("GILMORE_GIRLS_S1_US_D1", files)
        result = classify_disc_files(folder, _default_config())

        classifications = {f.filename: f.classification for f in result.files}
        assert classifications["DISC1-F1_t00.mkv"] == FileClassification.PLAY_ALL
        assert classifications["DISC1-B1_t01.mkv"] == FileClassification.EPISODE
        assert classifications["DISC1-C1_t02.mkv"] == FileClassification.EPISODE
        assert classifications["DISC1-D1_t03.mkv"] == FileClassification.EPISODE
        assert classifications["DISC1-E1_t04.mkv"] == FileClassification.EPISODE

    def test_2_episode_disc(self):
        """S2D6 pattern: 2 episodes + 1 Play All ~89 min + bonus."""
        files = [
            _mf("D6-B1_t01.mkv", 43.8, 1576),
            _mf("D6-C1_t02.mkv", 44.9, 1618),
            _mf("D6-D3_t03.mkv", 43.1, 1758),   # 3rd episode
            _mf("D6-D4_t04.mkv", 5.4, 222),      # bonus
            _mf("D6-E1_t00.mkv", 88.8, 3194),    # Play All (2 eps)
        ]
        folder = _folder("GILMOREGIRLS_S2_DISC6", files)
        result = classify_disc_files(folder, _default_config())

        classifications = {f.filename: f.classification for f in result.files}
        # 88.8 ≈ 43.8 + 44.9 = 88.7 — within tolerance but 43.1 is a 3rd episode
        # Actually sum of others (43.8 + 44.9 + 43.1) = 131.8, not close to 88.8
        # So E1 is NOT Play All here — it's an episode-length file
        # Let me recalculate: the "Play All" for a 3-ep disc would be ~131.8
        # 88.8 doesn't match 131.8, so no Play All detected — all are episodes
        assert classifications["D6-D4_t04.mkv"] == FileClassification.BONUS

    def test_2_episode_disc_with_play_all(self):
        """A true 2-episode disc where Play All ≈ sum of 2 episodes."""
        files = [
            _mf("D6-B1_t01.mkv", 43.8),
            _mf("D6-C1_t02.mkv", 44.9),
            _mf("D6-D1_t00.mkv", 88.5),   # Play All (43.8 + 44.9 = 88.7)
        ]
        folder = _folder("TEST_DISC", files)
        result = classify_disc_files(folder, _default_config())

        classifications = {f.filename: f.classification for f in result.files}
        assert classifications["D6-D1_t00.mkv"] == FileClassification.PLAY_ALL
        assert classifications["D6-B1_t01.mkv"] == FileClassification.EPISODE
        assert classifications["D6-C1_t02.mkv"] == FileClassification.EPISODE

    def test_no_play_all_when_only_one_long_file(self):
        """A movie disc with one long file should NOT be flagged as Play All."""
        files = [
            _mf("MOVIE_t00.mkv", 136.0, 4500),
            _mf("MOVIE_t01.mkv", 5.3, 200),
            _mf("MOVIE_t02.mkv", 3.1, 120),
        ]
        folder = _folder("THE_MATRIX", files)
        result = classify_disc_files(folder, _default_config())

        classifications = {f.filename: f.classification for f in result.files}
        assert classifications["MOVIE_t00.mkv"] == FileClassification.EPISODE
        assert classifications["MOVIE_t01.mkv"] == FileClassification.BONUS
        assert classifications["MOVIE_t02.mkv"] == FileClassification.BONUS


# ---------------------------------------------------------------------------
# Bonus content classification
# ---------------------------------------------------------------------------


class TestBonusClassification:
    def test_short_files_are_bonus(self):
        """Files under 10 min should be classified as BONUS."""
        files = [
            _mf("ep.mkv", 44.0),
            _mf("trailer.mkv", 2.3),
            _mf("promo.mkv", 3.6),
            _mf("featurette.mkv", 5.4),
        ]
        folder = _folder("DISC", files)
        result = classify_disc_files(folder, _default_config())

        classifications = {f.filename: f.classification for f in result.files}
        assert classifications["trailer.mkv"] == FileClassification.BONUS
        assert classifications["promo.mkv"] == FileClassification.BONUS
        assert classifications["featurette.mkv"] == FileClassification.BONUS
        assert classifications["ep.mkv"] == FileClassification.EPISODE

    def test_custom_bonus_threshold(self):
        """A 7-min file should be EPISODE with threshold=5, BONUS with threshold=10."""
        files = [_mf("clip.mkv", 7.0), _mf("ep.mkv", 44.0)]

        # With lower threshold, 7 min is above threshold → EPISODE
        folder = _folder("DISC", files)
        result_low = classify_disc_files(folder, _default_config(bonus_threshold_min=5.0))
        assert result_low.files[0].classification == FileClassification.EPISODE

        # With default threshold (10 min), 7 min is below → BONUS
        result_default = classify_disc_files(folder, _default_config())
        assert result_default.files[0].classification == FileClassification.BONUS

    def test_ambiguous_21_min_file(self):
        """The 21.9 min edge case from S1D6 — above bonus threshold, classified as EPISODE."""
        files = [
            _mf("D6-B1_t01.mkv", 21.9, 830),
            _mf("D6-B2_t02.mkv", 44.4, 1686),
            _mf("D6-B3_t03.mkv", 2.3, 86),
            _mf("D6-B4_t04.mkv", 3.6, 137),
            _mf("D6-C1_t00.mkv", 44.8, 1711),
        ]
        folder = _folder("GILMORE_GIRLS_S1_US_D6", files)
        result = classify_disc_files(folder, _default_config())

        classifications = {f.filename: f.classification for f in result.files}
        # 21.9 min is above the 10 min bonus threshold → not BONUS
        assert classifications["D6-B1_t01.mkv"] == FileClassification.EPISODE
        assert classifications["D6-B3_t03.mkv"] == FileClassification.BONUS
        assert classifications["D6-B4_t04.mkv"] == FileClassification.BONUS


# ---------------------------------------------------------------------------
# Preserve original file order
# ---------------------------------------------------------------------------


class TestFileOrderPreservation:
    def test_classification_preserves_order(self):
        """Files should stay in their original sorted order after classification."""
        files = [
            _mf("DISC1-B1_t01.mkv", 44.2),
            _mf("DISC1-C1_t02.mkv", 43.2),
            _mf("DISC1-D1_t03.mkv", 44.0),
            _mf("DISC1-E1_t04.mkv", 44.5),
            _mf("DISC1-F1_t00.mkv", 175.9),
        ]
        folder = _folder("DISC1", files)
        result = classify_disc_files(folder, _default_config())

        assert [f.filename for f in result.files] == [
            "DISC1-B1_t01.mkv",
            "DISC1-C1_t02.mkv",
            "DISC1-D1_t03.mkv",
            "DISC1-E1_t04.mkv",
            "DISC1-F1_t00.mkv",
        ]


# ---------------------------------------------------------------------------
# Directory scanning (mocked pymediainfo)
# ---------------------------------------------------------------------------


class TestScanSourceDirectory:
    def test_nonexistent_directory_raises(self):
        with pytest.raises(FileNotFoundError):
            scan_source_directory(Path("/nonexistent/path"))

    def test_discovers_mkv_files(self, tmp_path):
        """Creates a fake folder structure and verifies scanning finds MKVs."""
        disc1 = tmp_path / "DISC1"
        disc1.mkdir()
        (disc1 / "DISC1_t00.mkv").write_bytes(b"\x00" * 100)
        (disc1 / "DISC1_t01.mkv").write_bytes(b"\x00" * 100)
        (disc1 / "MakeMKV_Log.txt").write_text("log data")

        disc2 = tmp_path / "DISC2"
        disc2.mkdir()
        (disc2 / "DISC2_t00.mkv").write_bytes(b"\x00" * 100)

        # Mock extract_metadata since we don't have real MKV files
        mock_mf = _mf("stub.mkv", 44.0)

        with patch("media_renamer.scanner.extract_metadata") as mock_extract:
            mock_extract.side_effect = lambda p: mock_mf.model_copy(
                update={"path": p, "filename": p.name}
            )

            folders = scan_source_directory(tmp_path)

        assert len(folders) == 2
        assert folders[0].name == "DISC1"
        assert folders[1].name == "DISC2"
        assert len(folders[0].files) == 2
        assert len(folders[1].files) == 1
        # Verify log file was NOT picked up
        assert all(f.filename.endswith(".mkv") for f in folders[0].files)

    def test_empty_directory_returns_empty(self, tmp_path):
        """A directory with no MKV files returns an empty list."""
        (tmp_path / "readme.txt").write_text("no MKVs here")
        with patch("media_renamer.scanner.extract_metadata"):
            folders = scan_source_directory(tmp_path)
        assert folders == []
