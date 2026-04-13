"""Duration-based episode matching and movie identification."""

from __future__ import annotations

import logging

from media_renamer.config import AppConfig
from media_renamer.models import (
    EpisodeInfo,
    EpisodeMatch,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _score_confidence(diff_minutes: float, tolerance: float) -> MatchConfidence:
    """Score match confidence based on duration difference.

    HIGH:   diff ≤ 25% of tolerance  (e.g., ≤ 0.75 min with 3-min tolerance)
    MEDIUM: diff ≤ 75% of tolerance  (e.g., ≤ 2.25 min)
    LOW:    diff ≤ tolerance          (e.g., ≤ 3.0 min)
    """
    if diff_minutes <= tolerance * 0.25:
        return MatchConfidence.HIGH
    elif diff_minutes <= tolerance * 0.75:
        return MatchConfidence.MEDIUM
    else:
        return MatchConfidence.LOW


# ---------------------------------------------------------------------------
# Sequential disc episode offset
# ---------------------------------------------------------------------------

def compute_disc_episode_offset(
    disc_number: int,
    episodes_per_disc: int,
    total_episodes: int,
) -> int:
    """Compute the starting episode index (0-based) for a disc.

    For a multi-disc TV set where each disc has a fixed number of
    episodes (e.g., 4 per disc), disc 1 starts at episode 0, disc 2
    at episode 4, etc.

    The last disc may have fewer episodes.
    """
    if disc_number < 1:
        return 0
    offset = (disc_number - 1) * episodes_per_disc
    return min(offset, total_episodes)


def estimate_episodes_per_disc(
    episode_count: int,
    disc_count: int,
) -> int:
    """Estimate how many episodes are on each disc (except possibly the last).

    Uses ceiling division to distribute episodes as evenly as possible,
    but in practice TV DVD sets use a fixed count (e.g., 4) for all
    non-final discs.  We round up to handle the common case.
    """
    if disc_count <= 0:
        return episode_count
    return -(-episode_count // disc_count)  # ceiling division


# ---------------------------------------------------------------------------
# TV Episode matching
# ---------------------------------------------------------------------------

def match_episodes_by_duration(
    files: list[MediaFile],
    episodes: list[EpisodeInfo],
    config: AppConfig,
    episode_offset: int = 0,
) -> tuple[list[EpisodeMatch], list[MediaFile]]:
    """Match MKV files to TMDb episodes using duration comparison.

    Files are expected to be pre-sorted in episode order (by track
    position letter).  Only files classified as EPISODE are matched;
    PLAY_ALL and BONUS files are skipped.

    Args:
        files: Sorted list of MediaFile objects from a single disc.
        episodes: Full season episode list from TMDb.
        config: App configuration (tolerance settings).
        episode_offset: 0-based index into *episodes* where this disc starts.

    Returns:
        (matched, unmatched): matched EpisodeMatch list and unmatched MediaFile list.
    """
    tolerance_sec = config.duration_tolerance_min * 60

    # Filter to matchable files (EPISODE-classified only)
    candidates = [
        f for f in files
        if f.classification == FileClassification.EPISODE
    ]

    # Slice the episode list to the window this disc covers
    available_episodes = episodes[episode_offset:]

    matched: list[EpisodeMatch] = []
    unmatched: list[MediaFile] = []

    ep_cursor = 0  # index into available_episodes

    for file in candidates:
        if ep_cursor >= len(available_episodes):
            # No more episodes to match against
            unmatched.append(file)
            continue

        ep = available_episodes[ep_cursor]

        if ep.runtime_minutes is None:
            # No runtime data — match by position only, low confidence
            diff = 0.0
            confidence = MatchConfidence.LOW
        else:
            ep_duration_sec = ep.runtime_minutes * 60
            diff = abs(file.duration_seconds - ep_duration_sec)

            if diff > tolerance_sec:
                # Duration mismatch — skip this file, keep episode cursor
                unmatched.append(file)
                continue

            diff_min = diff / 60.0
            confidence = _score_confidence(diff_min, config.duration_tolerance_min)

        matched.append(EpisodeMatch(
            file=file,
            episode=ep,
            confidence=confidence,
            duration_diff_minutes=diff / 60.0,
        ))
        ep_cursor += 1  # advance episode cursor only on match

    return matched, unmatched


# ---------------------------------------------------------------------------
# Movie matching
# ---------------------------------------------------------------------------

def match_movie(
    files: list[MediaFile],
    movie: MovieMatch,
    config: AppConfig,
) -> tuple[MediaFile | None, MatchConfidence, list[MediaFile]]:
    """Match the longest file to a movie; classify the rest as extras.

    Returns:
        (main_file, confidence, extras): The main feature file, its match
        confidence, and a list of remaining extra files.
    """
    tolerance_sec = config.duration_tolerance_min * 60

    # Find episode-classified files (non-bonus, non-play-all)
    candidates = [
        f for f in files
        if f.classification in (FileClassification.EPISODE, FileClassification.MAIN_FEATURE)
    ]

    if not candidates:
        return None, MatchConfidence.LOW, []

    # Longest file is the main feature
    main = max(candidates, key=lambda f: f.duration_seconds)

    # Check duration against TMDb runtime
    if movie.runtime_minutes:
        movie_duration_sec = movie.runtime_minutes * 60
        diff = abs(main.duration_seconds - movie_duration_sec)
        diff_min = diff / 60.0

        if diff <= tolerance_sec:
            confidence = _score_confidence(diff_min, config.duration_tolerance_min)
        else:
            # Still the best candidate, but low confidence
            confidence = MatchConfidence.LOW
    else:
        confidence = MatchConfidence.LOW

    extras = [f for f in files if f is not main]
    return main, confidence, extras


# ---------------------------------------------------------------------------
# Post-match reclassification
# ---------------------------------------------------------------------------

def reclassify_unmatched(
    files: list[MediaFile],
    matched_filenames: set[str],
    config: AppConfig,
) -> list[MediaFile]:
    """Reclassify files that weren't matched to any episode.

    Files that were classified as EPISODE by the scanner but didn't match
    any TMDb episode (e.g., the 21.9 min file on S1D6) are reclassified
    as UNKNOWN for user review.
    """
    bonus_thresh_sec = config.bonus_threshold_min * 60
    result: list[MediaFile] = []

    for f in files:
        if f.filename in matched_filenames:
            result.append(f)
        elif f.classification in (FileClassification.PLAY_ALL, FileClassification.BONUS):
            result.append(f)
        else:
            # Was EPISODE but didn't match — reclassify
            new_class = FileClassification.BONUS if f.duration_seconds < bonus_thresh_sec else FileClassification.UNKNOWN
            result.append(f.model_copy(update={"classification": new_class}))

    return result
