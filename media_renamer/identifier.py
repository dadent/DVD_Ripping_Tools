"""TMDb API integration and content-type classification."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tmdbv3api import TMDb, Movie, TV, Season

from media_renamer.config import AppConfig
from media_renamer.models import (
    ContentType,
    DiscFolder,
    EpisodeInfo,
    FileClassification,
    MatchConfidence,
    MovieMatch,
    TVShowMatch,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes for raw search results (before matching)
# ---------------------------------------------------------------------------

@dataclass
class MovieSearchResult:
    """A single movie search hit from TMDb."""
    tmdb_id: int
    title: str
    year: int | None
    overview: str


@dataclass
class TVSearchResult:
    """A single TV show search hit from TMDb."""
    tmdb_id: int
    title: str
    first_air_year: int | None
    overview: str


# ---------------------------------------------------------------------------
# TMDb client wrapper
# ---------------------------------------------------------------------------

class TMDbClient:
    """Wraps the tmdbv3api library with error handling and typed returns."""

    def __init__(self, api_key: str) -> None:
        self._tmdb = TMDb()
        self._tmdb.api_key = api_key
        self._movie = Movie()
        self._tv = TV()
        self._season = Season()

    # --- Search ---------------------------------------------------------------

    def search_movie(self, title: str) -> list[MovieSearchResult]:
        """Search TMDb for movies matching *title*."""
        try:
            results = self._movie.search(title)
        except Exception:
            logger.exception("TMDb movie search failed for %r", title)
            return []

        hits: list[MovieSearchResult] = []
        for r in results:
            year = None
            release = getattr(r, "release_date", None)
            if release and len(str(release)) >= 4:
                try:
                    year = int(str(release)[:4])
                except ValueError:
                    pass
            hits.append(MovieSearchResult(
                tmdb_id=r.id,
                title=r.title,
                year=year,
                overview=getattr(r, "overview", "") or "",
            ))
        return hits

    def search_tv(self, title: str) -> list[TVSearchResult]:
        """Search TMDb for TV shows matching *title*."""
        try:
            results = self._tv.search(title)
        except Exception:
            logger.exception("TMDb TV search failed for %r", title)
            return []

        hits: list[TVSearchResult] = []
        for r in results:
            year = None
            first_air = getattr(r, "first_air_date", None)
            if first_air and len(str(first_air)) >= 4:
                try:
                    year = int(str(first_air)[:4])
                except ValueError:
                    pass
            hits.append(TVSearchResult(
                tmdb_id=r.id,
                title=r.name,
                first_air_year=year,
                overview=getattr(r, "overview", "") or "",
            ))
        return hits

    # --- Details --------------------------------------------------------------

    def get_movie_details(self, tmdb_id: int) -> MovieMatch | None:
        """Fetch full movie details and build a MovieMatch."""
        try:
            d = self._movie.details(tmdb_id)
        except Exception:
            logger.exception("TMDb movie details failed for id=%s", tmdb_id)
            return None

        year = None
        release = getattr(d, "release_date", None)
        if release and len(str(release)) >= 4:
            try:
                year = int(str(release)[:4])
            except ValueError:
                pass

        imdb_id = self._get_movie_imdb_id(tmdb_id)

        return MovieMatch(
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            title=d.title,
            year=year,
            runtime_minutes=getattr(d, "runtime", None),
        )

    def get_season_episodes(
        self, tv_id: int, season_number: int
    ) -> list[EpisodeInfo]:
        """Fetch all episodes for a TV season with runtimes."""
        try:
            s = self._season.details(tv_id, season_number)
        except Exception:
            logger.exception(
                "TMDb season details failed for tv=%s season=%s",
                tv_id, season_number,
            )
            return []

        episodes: list[EpisodeInfo] = []
        for ep in s.episodes:
            try:
                episodes.append(EpisodeInfo(
                    season_number=season_number,
                    episode_number=ep.episode_number,
                    title=getattr(ep, "name", None) or f"Episode {ep.episode_number}",
                    runtime_minutes=getattr(ep, "runtime", None),
                ))
            except (AttributeError, TypeError):
                logger.warning("Skipping malformed episode in tv=%s season=%s", tv_id, season_number)
        return episodes

    # --- External IDs ---------------------------------------------------------

    def _get_movie_imdb_id(self, tmdb_id: int) -> str | None:
        """Get the IMDB ID for a movie."""
        try:
            ext = self._movie.external_ids(tmdb_id)
            return getattr(ext, "imdb_id", None)
        except Exception:
            logger.exception("TMDb movie external_ids failed for id=%s", tmdb_id)
            return None

    def get_tv_external_ids(self, tv_id: int) -> dict[str, int | str | None]:
        """Get external IDs (IMDB, TVDB) for a TV show.

        Returns dict with keys 'imdb_id' and 'tvdb_id'.
        """
        try:
            ext = self._tv.external_ids(tv_id)
            return {
                "imdb_id": getattr(ext, "imdb_id", None),
                "tvdb_id": getattr(ext, "tvdb_id", None),
            }
        except Exception:
            logger.exception("TMDb TV external_ids failed for id=%s", tv_id)
            return {"imdb_id": None, "tvdb_id": None}

    def build_tv_match(
        self,
        tv_id: int,
        season_number: int,
    ) -> TVShowMatch | None:
        """Build a TVShowMatch with external IDs and episode data."""
        try:
            d = self._tv.details(tv_id)
        except Exception:
            logger.exception("TMDb TV details failed for id=%s", tv_id)
            return None

        year = None
        first_air = getattr(d, "first_air_date", None)
        if first_air and len(str(first_air)) >= 4:
            try:
                year = int(str(first_air)[:4])
            except ValueError:
                pass

        ext = self.get_tv_external_ids(tv_id)

        return TVShowMatch(
            tmdb_id=tv_id,
            tvdb_id=ext.get("tvdb_id"),
            title=d.name,
            year=year,
            season_number=season_number,
        )


# ---------------------------------------------------------------------------
# Content type classification (heuristic, no API calls)
# ---------------------------------------------------------------------------

def classify_content_type(folder: DiscFolder, config: AppConfig) -> ContentType:
    """Guess whether a folder contains a Movie or TV Series based on file patterns.

    Heuristics:
      - If there are ≥3 episode-classified files with similar durations → TV_SERIES
      - If there is exactly 1 episode-classified file (long) with only bonus
        files alongside it → MOVIE
      - Otherwise → UNKNOWN (needs LLM or user input)
    """
    bonus_thresh = config.bonus_threshold_min * 60

    episode_files = [
        f for f in folder.files
        if f.classification in (FileClassification.EPISODE, FileClassification.UNKNOWN)
        and f.duration_seconds >= bonus_thresh
    ]
    bonus_files = [
        f for f in folder.files
        if f.classification == FileClassification.BONUS
    ]

    if not episode_files:
        return ContentType.UNKNOWN

    if len(episode_files) == 1:
        # Single long file + bonus = likely a movie disc
        return ContentType.MOVIE

    # Multiple long files — check if they have similar durations (TV pattern)
    durations = [f.duration_seconds for f in episode_files]
    avg_dur = sum(durations) / len(durations)
    # TV episodes typically have durations within ±30% of each other
    if avg_dur > 0 and all(abs(d - avg_dur) / avg_dur < 0.3 for d in durations):
        return ContentType.TV_SERIES

    # Mixed durations — could be anything
    return ContentType.UNKNOWN
