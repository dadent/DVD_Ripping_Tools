"""Directory scanning, MKV metadata extraction, and file classification."""

from __future__ import annotations

import logging
from pathlib import Path

from pymediainfo import MediaInfo

from media_renamer.config import AppConfig
from media_renamer.models import DiscFolder, FileClassification, MediaFile

logger = logging.getLogger(__name__)

_MKV_EXTENSIONS = {".mkv", ".MKV"}


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def extract_metadata(path: Path) -> MediaFile:
    """Extract metadata from a single MKV file using pymediainfo.

    Returns a MediaFile with duration, audio/subtitle info, resolution,
    chapter count, and file size populated.  Classification is left as
    UNKNOWN — call classify_disc_files() afterwards.
    """
    mi = MediaInfo.parse(str(path))

    duration_ms: float = 0.0
    video_resolution: str | None = None
    audio_tracks: list[str] = []
    audio_count = 0
    subtitle_tracks: list[str] = []
    subtitle_count = 0
    chapter_count = 0
    chapter_names: list[str] = []

    for track in mi.tracks:
        if track.track_type == "General":
            duration_ms = float(track.duration or 0)

        elif track.track_type == "Video":
            if track.width and track.height:
                video_resolution = f"{track.width}x{track.height}"

        elif track.track_type == "Audio":
            audio_count += 1
            lang = track.language
            if lang and lang not in audio_tracks:
                audio_tracks.append(lang)

        elif track.track_type == "Text":
            subtitle_count += 1
            lang = track.language
            if lang and lang not in subtitle_tracks:
                subtitle_tracks.append(lang)

        elif track.track_type == "Menu":
            # Chapter markers are stored as timestamp attributes on Menu tracks.
            # They appear as attributes like '00_04_18758' on the track object.
            menu_data = track.to_data()
            # Count keys that look like timestamp chapter markers (NN_NN_NNNNN)
            chapter_entries = [
                k for k in menu_data
                if isinstance(k, str) and len(k) >= 8 and k.replace("_", "").isdigit()
            ]
            chapter_count = len(chapter_entries)
            # Chapter names: pymediainfo may store values for those keys
            for key in chapter_entries:
                val = menu_data.get(key)
                if val and isinstance(val, str) and val.strip():
                    chapter_names.append(val.strip())

    try:
        file_size = path.stat().st_size
    except OSError:
        file_size = 0

    return MediaFile(
        path=path,
        filename=path.name,
        duration_seconds=duration_ms / 1000.0,
        audio_track_count=audio_count,
        audio_languages=audio_tracks,
        subtitle_track_count=subtitle_count,
        subtitle_languages=subtitle_tracks,
        video_resolution=video_resolution,
        chapter_count=chapter_count,
        chapter_names=chapter_names,
        file_size_bytes=file_size,
    )


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------

def scan_source_directory(source: Path) -> list[DiscFolder]:
    """Walk *source* and return one DiscFolder per sub-folder containing MKVs.

    MKV files directly inside *source* (not in a sub-folder) are grouped
    into a DiscFolder named after *source* itself.

    Folders are returned sorted alphabetically by name.
    Files within each folder are sorted by the file-ordering heuristic
    (track position letter gives episode order).
    """
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source}")

    # Collect MKV paths grouped by their immediate parent directory
    folder_map: dict[Path, list[Path]] = {}

    for mkv_path in source.rglob("*"):
        if mkv_path.suffix in _MKV_EXTENSIONS and mkv_path.is_file():
            parent = mkv_path.parent
            folder_map.setdefault(parent, []).append(mkv_path)

    # Build DiscFolder objects
    folders: list[DiscFolder] = []
    for folder_path, mkv_paths in sorted(folder_map.items()):
        mkv_paths_sorted = sort_files_for_episode_order(mkv_paths)

        media_files: list[MediaFile] = []
        for p in mkv_paths_sorted:
            try:
                mf = extract_metadata(p)
                media_files.append(mf)
            except Exception:
                logger.warning("Skipping %s — failed to extract metadata", p)

        if media_files:
            folders.append(
                DiscFolder(
                    path=folder_path,
                    name=folder_path.name,
                    files=media_files,
                )
            )

    return folders


# ---------------------------------------------------------------------------
# File ordering heuristic
# ---------------------------------------------------------------------------

def sort_files_for_episode_order(paths: list[Path]) -> list[Path]:
    """Sort MKV file paths into likely episode order.

    MakeMKV file names follow the pattern:
        {DiscLabel}-{TrackPosition}_t{TrackNumber}.mkv

    The track position letter (B, C, D, E, F, G…) indicates the disc
    position and gives the correct episode order.  The track number
    (t00, t01…) is assigned by MakeMKV and is NOT reliably sequential.

    We sort alphabetically by filename, which naturally orders by the
    track position letter.
    """
    return sorted(paths, key=lambda p: p.name)


# ---------------------------------------------------------------------------
# Classification heuristics
# ---------------------------------------------------------------------------

def classify_disc_files(folder: DiscFolder, config: AppConfig) -> DiscFolder:
    """Classify each file in *folder* as PLAY_ALL, BONUS, EPISODE, or UNKNOWN.

    Algorithm:
      1. Identify episode-length candidates (duration ≥ bonus_threshold).
      2. Among candidates, detect "Play All" tracks whose duration ≈ the
         sum of all *other* candidates (±play_all_tolerance).
      3. Files shorter than bonus_threshold are BONUS.
      4. Remaining candidates are EPISODE (if there are multiple) or
         MAIN_FEATURE (if only one long file — likely a movie disc, but
         we leave final Movie/TV classification to later phases).

    Returns a *new* DiscFolder with updated file classifications.
    """
    bonus_thresh_sec = config.bonus_threshold_min * 60
    play_all_tol_sec = config.play_all_tolerance_min * 60

    classified: list[MediaFile] = []

    # --- Step 1: split into candidates vs definite bonus ---
    candidates: list[MediaFile] = []
    bonus_files: list[MediaFile] = []

    for mf in folder.files:
        if mf.duration_seconds < bonus_thresh_sec:
            bonus_files.append(mf.model_copy(update={"classification": FileClassification.BONUS}))
        else:
            candidates.append(mf)

    # --- Step 2: detect Play All among candidates ---
    play_all_indices: set[int] = set()

    if len(candidates) >= 2:
        for i, candidate in enumerate(candidates):
            # Sum durations of all OTHER candidates
            others_sum = sum(
                c.duration_seconds for j, c in enumerate(candidates) if j != i
            )
            if abs(candidate.duration_seconds - others_sum) <= play_all_tol_sec:
                play_all_indices.add(i)

    # Guard: if ALL candidates are marked Play All, none of them actually are.
    # A true Play All is ONE concatenated track, not every track.
    if play_all_indices and play_all_indices == set(range(len(candidates))):
        play_all_indices.clear()

    # --- Step 3: assign final classifications ---
    episode_candidates: list[MediaFile] = []
    for i, candidate in enumerate(candidates):
        if i in play_all_indices:
            classified.append(
                candidate.model_copy(update={"classification": FileClassification.PLAY_ALL})
            )
        else:
            episode_candidates.append(candidate)

    # If exactly 1 non-Play-All candidate remains, it's likely a main feature
    # (movie disc), but we use EPISODE here — the Identify phase will refine.
    for ec in episode_candidates:
        classified.append(
            ec.model_copy(update={"classification": FileClassification.EPISODE})
        )

    classified.extend(bonus_files)

    # Re-sort into the original episode order
    original_order = {mf.filename: idx for idx, mf in enumerate(folder.files)}
    classified.sort(key=lambda mf: original_order.get(mf.filename, 999))

    return folder.model_copy(update={"files": classified})
