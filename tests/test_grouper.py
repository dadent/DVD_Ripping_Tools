"""Tests for the disc grouping module (media_renamer/grouper.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from media_renamer.grouper import DiscGroup, _normalize_title, group_tv_discs
from media_renamer.models import DiscFolder, MediaFile
from media_renamer.prompts import FolderInterpretation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _disc(name: str) -> DiscFolder:
    return DiscFolder(path=Path(f"D:/Video/processed/{name}"), name=name, files=[])


def _interp(title: str, content_type: str = "tv", season: int | None = None, disc: int | None = None) -> FolderInterpretation:
    return FolderInterpretation(
        title=title,
        content_type=content_type,
        season=season,
        disc=disc,
        confidence="high",
    )


# ---------------------------------------------------------------------------
# _normalize_title
# ---------------------------------------------------------------------------


class TestNormalizeTitle:
    def test_lowercase_and_strip(self):
        assert _normalize_title("  GILMORE GIRLS  ") == "gilmore girls"

    def test_removes_us_suffix(self):
        # Region tokens are preserved — different shows stay separate
        assert _normalize_title("GILMORE GIRLS US") == "gilmore girls us"

    def test_preserves_uk_suffix(self):
        assert _normalize_title("DOCTOR WHO UK") == "doctor who uk"

    def test_collapses_whitespace(self):
        assert _normalize_title("THE   BIG   SHOW") == "the big show"


# ---------------------------------------------------------------------------
# group_tv_discs
# ---------------------------------------------------------------------------


class TestGroupTvDiscs:
    def test_groups_same_show_season(self):
        """Multiple discs of same show+season → one group."""
        discs = [_disc(f"GG_S1_D{i}") for i in range(1, 7)]
        interps = [_interp("Gilmore Girls", season=1, disc=i) for i in range(1, 7)]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 1
        assert groups[0].disc_count == 6
        assert groups[0].title == "Gilmore Girls"
        assert groups[0].season == 1
        assert len(ungrouped) == 0

    def test_separate_seasons_separate_groups(self):
        """S1 and S2 discs → two separate groups."""
        discs = [
            _disc("GG_S1_D1"), _disc("GG_S1_D2"),
            _disc("GG_S2_D1"), _disc("GG_S2_D2"),
        ]
        interps = [
            _interp("Gilmore Girls", season=1, disc=1),
            _interp("Gilmore Girls", season=1, disc=2),
            _interp("Gilmore Girls", season=2, disc=1),
            _interp("Gilmore Girls", season=2, disc=2),
        ]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 2
        assert {g.season for g in groups} == {1, 2}
        assert len(ungrouped) == 0

    def test_movies_are_ungrouped(self):
        """Movie folders go to ungrouped list."""
        discs = [_disc("THE_MATRIX"), _disc("GG_S1_D1"), _disc("GG_S1_D2")]
        interps = [
            _interp("The Matrix", content_type="movie"),
            _interp("Gilmore Girls", season=1, disc=1),
            _interp("Gilmore Girls", season=1, disc=2),
        ]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 1
        assert len(ungrouped) == 1
        assert ungrouped[0][0].name == "THE_MATRIX"

    def test_single_tv_disc_is_ungrouped(self):
        """A lone TV disc (no partner) goes to ungrouped."""
        discs = [_disc("GG_S1_D1")]
        interps = [_interp("Gilmore Girls", season=1, disc=1)]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 0
        assert len(ungrouped) == 1

    def test_unknown_content_type_is_ungrouped(self):
        """Unknown content type goes to ungrouped."""
        discs = [_disc("MYSTERY_D1"), _disc("MYSTERY_D2")]
        interps = [
            _interp("Mystery", content_type="unknown", disc=1),
            _interp("Mystery", content_type="unknown", disc=2),
        ]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 0
        assert len(ungrouped) == 2

    def test_mixed_input(self):
        """TV groups + movie + single TV disc → correct partition."""
        discs = [
            _disc("GG_S1_D1"), _disc("GG_S1_D2"), _disc("GG_S1_D3"),
            _disc("THE_MATRIX"),
            _disc("FRIENDS_S1_D1"),
        ]
        interps = [
            _interp("Gilmore Girls", season=1, disc=1),
            _interp("Gilmore Girls", season=1, disc=2),
            _interp("Gilmore Girls", season=1, disc=3),
            _interp("The Matrix", content_type="movie"),
            _interp("Friends", season=1, disc=1),
        ]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 1
        assert groups[0].disc_count == 3
        assert len(ungrouped) == 2  # Matrix + lone Friends disc

    def test_title_normalization_groups_variants(self):
        """Same title (case-insensitive) should still group."""
        discs = [_disc("GILMORE_GIRLS_S1_D1"), _disc("GILMOREGIRLS_S1_D2")]
        interps = [
            _interp("Gilmore Girls", season=1, disc=1),
            _interp("Gilmore Girls", season=1, disc=2),
        ]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 1
        assert groups[0].disc_count == 2

    def test_region_variants_stay_separate(self):
        """'The Office US' and 'The Office UK' must NOT group together."""
        discs = [_disc("OFFICE_US_D1"), _disc("OFFICE_UK_D1")]
        interps = [
            _interp("The Office US", season=1, disc=1),
            _interp("The Office UK", season=1, disc=1),
        ]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 0  # neither has 2+ discs
        assert len(ungrouped) == 2

    def test_no_season_defaults_to_1(self):
        """Folders without explicit season default to season 1."""
        discs = [_disc("GG_D1"), _disc("GG_D2")]
        interps = [
            _interp("Gilmore Girls", season=None, disc=1),
            _interp("Gilmore Girls", season=None, disc=2),
        ]

        groups, ungrouped = group_tv_discs(discs, interps)

        assert len(groups) == 1
        assert groups[0].season == 1


# ---------------------------------------------------------------------------
# DiscGroup.sorted_discs
# ---------------------------------------------------------------------------


class TestDiscGroupSorting:
    def test_sorts_by_disc_number(self):
        """Discs should be sorted by disc number regardless of input order."""
        discs = [_disc("GG_S1_D3"), _disc("GG_S1_D1"), _disc("GG_S1_D2")]
        interps = [
            _interp("Gilmore Girls", season=1, disc=3),
            _interp("Gilmore Girls", season=1, disc=1),
            _interp("Gilmore Girls", season=1, disc=2),
        ]

        groups, _ = group_tv_discs(discs, interps)
        sorted_d = groups[0].sorted_discs()

        disc_nums = [interp.disc for _, interp in sorted_d]
        assert disc_nums == [1, 2, 3]

    def test_empty_group(self):
        """Edge case: DiscGroup with no discs."""
        group = DiscGroup(title="Test", season=1, content_type="tv", discs=[])
        assert group.sorted_discs() == []
        assert group.disc_count == 0
