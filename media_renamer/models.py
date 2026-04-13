"""Pydantic data models for the Media Renamer pipeline."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ContentType(str, Enum):
    """Classification of a disc folder's content."""
    MOVIE = "movie"
    TV_SERIES = "tv_series"
    UNKNOWN = "unknown"


class FileClassification(str, Enum):
    """Classification of an individual MKV file on a disc."""
    MAIN_FEATURE = "main_feature"
    EPISODE = "episode"
    PLAY_ALL = "play_all"
    BONUS = "bonus"
    UNKNOWN = "unknown"


class MatchConfidence(str, Enum):
    """Confidence level for a file-to-media match."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionTaken(str, Enum):
    """Outcome for a single file after processing."""
    MOVED = "moved"
    SKIPPED = "skipped"
    ERROR = "error"


# ---------------------------------------------------------------------------
# MKV file metadata
# ---------------------------------------------------------------------------

class MediaFile(BaseModel):
    """Metadata extracted from a single MKV file."""
    path: Path
    filename: str
    duration_seconds: float = Field(description="Duration in seconds")
    audio_track_count: int = 0
    audio_languages: list[str] = Field(default_factory=list)
    subtitle_track_count: int = 0
    subtitle_languages: list[str] = Field(default_factory=list)
    video_resolution: str | None = None
    chapter_count: int = 0
    chapter_names: list[str] = Field(default_factory=list)
    file_size_bytes: int = 0
    classification: FileClassification = FileClassification.UNKNOWN

    @property
    def duration_minutes(self) -> float:
        """Duration in minutes (convenience)."""
        return self.duration_seconds / 60.0


# ---------------------------------------------------------------------------
# Disc folder
# ---------------------------------------------------------------------------

class DiscFolder(BaseModel):
    """A single MakeMKV output folder representing one disc."""
    path: Path
    name: str = Field(description="Folder name (disc label)")
    files: list[MediaFile] = Field(default_factory=list)
    content_type: ContentType = ContentType.UNKNOWN
    parsed_title: str | None = None
    parsed_season: int | None = None
    parsed_disc: int | None = None


# ---------------------------------------------------------------------------
# TMDb / match results
# ---------------------------------------------------------------------------

class MovieMatch(BaseModel):
    """A proposed movie match for a disc folder."""
    tmdb_id: int
    imdb_id: str | None = None
    title: str
    year: int | None = None
    runtime_minutes: int | None = None
    confidence: MatchConfidence = MatchConfidence.MEDIUM


class EpisodeInfo(BaseModel):
    """TMDb episode metadata."""
    season_number: int
    episode_number: int
    title: str
    runtime_minutes: int | None = None


class EpisodeMatch(BaseModel):
    """A proposed mapping from an MKV file to a TV episode."""
    file: MediaFile
    episode: EpisodeInfo
    confidence: MatchConfidence = MatchConfidence.MEDIUM
    duration_diff_minutes: float = 0.0


class TVShowMatch(BaseModel):
    """A proposed TV show match for a disc folder."""
    tmdb_id: int
    tvdb_id: int | None = None
    title: str
    year: int | None = None
    season_number: int | None = None
    episode_matches: list[EpisodeMatch] = Field(default_factory=list)
    confidence: MatchConfidence = MatchConfidence.MEDIUM


# ---------------------------------------------------------------------------
# Processing results
# ---------------------------------------------------------------------------

class FileAction(BaseModel):
    """Record of what happened to a single file."""
    source_path: Path
    dest_path: Path | None = None
    action: ActionTaken
    description: str = ""


class ProcessingResult(BaseModel):
    """Summary of processing a single disc folder."""
    folder_name: str
    content_type: ContentType
    matched_title: str | None = None
    file_actions: list[FileAction] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def moved_count(self) -> int:
        return sum(1 for a in self.file_actions if a.action == ActionTaken.MOVED)

    @property
    def skipped_count(self) -> int:
        return sum(1 for a in self.file_actions if a.action == ActionTaken.SKIPPED)

    @property
    def error_count(self) -> int:
        return sum(1 for a in self.file_actions if a.action == ActionTaken.ERROR)
