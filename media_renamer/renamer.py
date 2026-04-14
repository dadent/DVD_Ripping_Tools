"""File operations — build Plex directory structure and move/rename files."""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from media_renamer.models import (
    ActionTaken,
    ContentType,
    EpisodeMatch,
    FileAction,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
    ProcessingResult,
    TVShowMatch,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------

# Characters illegal in Windows filenames (also avoid on other OSes for safety)
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are illegal in file/folder names."""
    cleaned = _ILLEGAL_CHARS.sub("", name)
    # Collapse multiple spaces / dots at edges
    cleaned = cleaned.strip(". ")
    return cleaned or "untitled"


# ---------------------------------------------------------------------------
# Plex path builders
# ---------------------------------------------------------------------------

def _show_dir_name(show: TVShowMatch) -> str:
    """Build the top-level TV show folder name."""
    year_str = f" ({show.year})" if show.year else ""
    tvdb_str = f" {{tvdb-{show.tvdb_id}}}" if show.tvdb_id else ""
    return sanitize_filename(f"{show.title}{year_str}{tvdb_str}")


def _movie_dir_name(movie: MovieMatch) -> str:
    """Build the movie folder name."""
    year_str = f" ({movie.year})" if movie.year else ""
    imdb_str = f" {{imdb-{movie.imdb_id}}}" if movie.imdb_id else ""
    return sanitize_filename(f"{movie.title}{year_str}{imdb_str}")


def build_tv_episode_dest(
    dest_root: Path,
    show: TVShowMatch,
    ep: EpisodeMatch,
) -> Path:
    """Build the full destination path for a TV episode file.

    Template: {dest}/TV Shows/{Show (Year) {tvdb-ID}}/Season NN/{Show (Year) - sNNeNN - Title}.mkv
    """
    show_dir = _show_dir_name(show)
    season_dir = f"Season {ep.episode.season_number:02d}"
    year_str = f" ({show.year})" if show.year else ""
    ep_filename = sanitize_filename(
        f"{show.title}{year_str} - "
        f"s{ep.episode.season_number:02d}e{ep.episode.episode_number:02d} - "
        f"{ep.episode.title}"
    )
    # Preserve the original file extension
    ext = ep.file.path.suffix or ".mkv"
    return dest_root / "TV Shows" / show_dir / season_dir / f"{ep_filename}{ext}"


def build_tv_extra_dest(
    dest_root: Path,
    show: TVShowMatch,
    file: MediaFile,
) -> Path:
    """Build the destination path for a TV extra/featurette.

    Template: {dest}/TV Shows/{Show (Year) {tvdb-ID}}/Featurettes/{original_name}.mkv
    """
    show_dir = _show_dir_name(show)
    return dest_root / "TV Shows" / show_dir / "Featurettes" / file.filename


def build_movie_dest(
    dest_root: Path,
    movie: MovieMatch,
) -> Path:
    """Build the full destination path for a movie file.

    Template: {dest}/Movies/{Movie (Year) {imdb-ID}}/{Movie (Year) {imdb-ID}}.mkv
    """
    movie_dir = _movie_dir_name(movie)
    return dest_root / "Movies" / movie_dir / f"{movie_dir}.mkv"


def build_movie_extra_dest(
    dest_root: Path,
    movie: MovieMatch,
    file: MediaFile,
    extra_type: str = "featurette",
    index: int = 1,
) -> Path:
    """Build the destination path for a movie extra.

    Template: {dest}/Movies/{Movie (Year) {imdb-ID}}/{Movie (Year) - {type}-{N}}.mkv
    """
    movie_dir = _movie_dir_name(movie)
    year_str = f" ({movie.year})" if movie.year else ""
    extra_filename = sanitize_filename(
        f"{movie.title}{year_str} - {extra_type}-{index}"
    )
    ext = file.path.suffix or ".mkv"
    return dest_root / "Movies" / movie_dir / f"{extra_filename}{ext}"


# ---------------------------------------------------------------------------
# File move operation
# ---------------------------------------------------------------------------

def move_file(source: Path, dest: Path, dry_run: bool = False) -> FileAction:
    """Move a single file from source to dest with error handling.

    Creates parent directories as needed.  In dry-run mode, no files
    are actually moved.
    """
    try:
        if dry_run:
            return FileAction(
                source_path=source,
                dest_path=dest,
                action=ActionTaken.MOVED,
                description=f"[DRY RUN] Would move to {dest}",
            )

        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            logger.warning("Destination already exists, skipping: %s", dest)
            return FileAction(
                source_path=source,
                dest_path=dest,
                action=ActionTaken.ERROR,
                description=f"Destination already exists: {dest}",
            )

        # Use shutil.move for cross-device compatibility
        shutil.move(str(source), str(dest))

        logger.info("Moved: %s → %s", source, dest)
        return FileAction(
            source_path=source,
            dest_path=dest,
            action=ActionTaken.MOVED,
            description=f"Moved to {dest}",
        )
    except Exception as e:
        logger.exception("Failed to move %s → %s", source, dest)
        return FileAction(
            source_path=source,
            dest_path=dest,
            action=ActionTaken.ERROR,
            description=f"Move failed: {e}",
        )


# ---------------------------------------------------------------------------
# Batch move operations
# ---------------------------------------------------------------------------

def execute_tv_moves(
    dest_root: Path,
    show: TVShowMatch,
    matched: list[EpisodeMatch],
    extras: list[MediaFile],
    skipped: list[MediaFile],
    dry_run: bool = False,
) -> ProcessingResult:
    """Move all TV episode files + extras to Plex structure.

    Returns a ProcessingResult recording every action.
    """
    result = ProcessingResult(
        folder_name=show.title,
        content_type=ContentType.TV_SERIES,
        matched_title=show.title,
    )

    # Move matched episodes
    for em in matched:
        dest_path = build_tv_episode_dest(dest_root, show, em)
        action = move_file(em.file.path, dest_path, dry_run=dry_run)
        result.file_actions.append(action)

    # Move extras to Featurettes/
    for ex in extras:
        dest_path = build_tv_extra_dest(dest_root, show, ex)
        action = move_file(ex.path, dest_path, dry_run=dry_run)
        result.file_actions.append(action)

    # Record skipped files (play_all)
    for sf in skipped:
        result.file_actions.append(FileAction(
            source_path=sf.path,
            action=ActionTaken.SKIPPED,
            description=f"Skipped ({sf.classification.value})",
        ))

    return result


def execute_movie_moves(
    dest_root: Path,
    movie: MovieMatch,
    main_file: MediaFile | None,
    extras: list[MediaFile],
    dry_run: bool = False,
) -> ProcessingResult:
    """Move movie main feature + extras to Plex structure."""
    result = ProcessingResult(
        folder_name=movie.title,
        content_type=ContentType.MOVIE,
        matched_title=movie.title,
    )

    # Move main feature
    if main_file:
        dest_path = build_movie_dest(dest_root, movie)
        action = move_file(main_file.path, dest_path, dry_run=dry_run)
        result.file_actions.append(action)

    # Move extras — auto-increment past any existing featurette files
    extra_idx = 1
    if not dry_run:
        movie_dir = build_movie_dest(dest_root, movie).parent
        year_str = f" ({movie.year})" if movie.year else ""
        while (movie_dir / f"{sanitize_filename(f'{movie.title}{year_str}')} - featurette-{extra_idx}.mkv").exists():
            extra_idx += 1

    for ex in extras:
        if ex.classification == FileClassification.PLAY_ALL:
            result.file_actions.append(FileAction(
                source_path=ex.path,
                action=ActionTaken.SKIPPED,
                description="Skipped (play_all)",
            ))
            continue

        dest_path = build_movie_extra_dest(
            dest_root, movie, ex, extra_type="featurette", index=extra_idx,
        )
        action = move_file(ex.path, dest_path, dry_run=dry_run)
        result.file_actions.append(action)
        extra_idx += 1

    return result


# ---------------------------------------------------------------------------
# Processing log
# ---------------------------------------------------------------------------

def write_processing_log(
    dest_root: Path,
    results: list[ProcessingResult],
    dry_run: bool = False,
) -> Path:
    """Write a JSON processing log to {dest_root}/media_renamer.log.

    Returns the path to the log file.
    """
    log_path = dest_root / "media_renamer.log"

    entries = []
    for r in results:
        folder_entry = {
            "folder": r.folder_name,
            "content_type": r.content_type.value if hasattr(r.content_type, 'value') else str(r.content_type),
            "matched_title": r.matched_title,
            "actions": [],
            "errors": r.errors,
        }
        for a in r.file_actions:
            folder_entry["actions"].append({
                "source": str(a.source_path),
                "dest": str(a.dest_path) if a.dest_path else None,
                "action": a.action.value,
                "description": a.description,
            })
        entries.append(folder_entry)

    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "folders_processed": len(results),
        "total_moved": sum(r.moved_count for r in results),
        "total_skipped": sum(r.skipped_count for r in results),
        "total_errors": sum(r.error_count for r in results),
        "results": entries,
    }

    if dry_run:
        # In dry-run, don't write the log file, just return the path
        logger.info("[DRY RUN] Would write log to %s", log_path)
        return log_path

    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Append to existing log if present
    existing: list[dict] = []
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
        except (json.JSONDecodeError, Exception):
            existing = []

    existing.append(log_data)

    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, default=str)
        logger.info("Processing log written to %s", log_path)
    except OSError:
        logger.warning("Could not write processing log to %s", log_path)

    return log_path
