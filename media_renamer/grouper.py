"""Auto-grouping of TV disc folders by show + season."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from media_renamer.models import DiscFolder
from media_renamer.prompts import FolderInterpretation

logger = logging.getLogger(__name__)


@dataclass
class DiscGroup:
    """A batch of disc folders that belong to the same TV show + season."""

    title: str
    season: int
    content_type: str  # "tv"
    discs: list[tuple[DiscFolder, FolderInterpretation]] = field(default_factory=list)

    @property
    def disc_count(self) -> int:
        return len(self.discs)

    def sorted_discs(self) -> list[tuple[DiscFolder, FolderInterpretation]]:
        """Return discs sorted by disc number (ascending)."""
        return sorted(self.discs, key=lambda pair: pair[1].disc or _parse_disc_number(pair[0].name))


def _normalize_title(title: str) -> str:
    """Normalize a title for grouping comparison.

    Lowercases, strips whitespace/underscores, removes common suffixes like
    'US' so that 'GILMORE_GIRLS_S1_US_D1' and 'GILMORE_GIRLS_S2_D1' group
    under the same show.
    """
    t = title.lower().strip()
    # Remove common region/edition suffixes
    t = re.sub(r"\b(us|uk|au)\b", "", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_disc_number(folder_name: str) -> int:
    """Extract disc number from folder name (fallback for FolderInterpretation.disc)."""
    upper = folder_name.upper()
    m = re.search(r"D(\d+)|DISC\s*(\d+)", upper)
    if m:
        return int(m.group(1) or m.group(2))
    return 1


def group_tv_discs(
    discs: list[DiscFolder],
    interpretations: list[FolderInterpretation],
) -> tuple[list[DiscGroup], list[tuple[DiscFolder, FolderInterpretation]]]:
    """Group TV disc folders by show + season.

    Returns:
        groups: list of DiscGroup, each containing 2+ related TV discs
        ungrouped: list of (disc, interp) pairs that couldn't be grouped
                   (movies, unknown content, or single TV discs)
    """
    # Build grouping buckets: key = (normalized_title, season)
    buckets: dict[tuple[str, int], list[tuple[DiscFolder, FolderInterpretation]]] = {}

    ungrouped: list[tuple[DiscFolder, FolderInterpretation]] = []

    for disc, interp in zip(discs, interpretations):
        if interp.content_type != "tv":
            ungrouped.append((disc, interp))
            continue

        season = interp.season or 1
        key = (_normalize_title(interp.title), season)
        buckets.setdefault(key, []).append((disc, interp))

    # Convert buckets to DiscGroups (only groups with 2+ discs)
    groups: list[DiscGroup] = []
    for (norm_title, season), members in sorted(buckets.items()):
        if len(members) < 2:
            # Single disc — process individually
            ungrouped.extend(members)
            continue

        # Use the first disc's original title (un-normalized) for display
        display_title = members[0][1].title
        group = DiscGroup(
            title=display_title,
            season=season,
            content_type="tv",
            discs=members,
        )
        groups.append(group)

    return groups, ungrouped
