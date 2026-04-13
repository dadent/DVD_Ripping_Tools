"""LLM integration — OpenAI client, prompt templates, and fallback parsing."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from openai import OpenAI

from media_renamer.config import AppConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured response types
# ---------------------------------------------------------------------------

@dataclass
class FolderInterpretation:
    """LLM's interpretation of a MakeMKV disc folder name."""
    title: str
    season: int | None = None
    disc: int | None = None
    content_type: str = "unknown"  # "movie", "tv", "unknown"
    confidence: str = "medium"     # "high", "medium", "low"
    notes: str = ""


@dataclass
class ExtraClassification:
    """LLM's classification of a bonus/extra file."""
    extra_type: str      # behindthescenes, featurette, trailer, interview, deleted, other
    label: str = ""      # human-readable label if identifiable
    confidence: str = "medium"


# ---------------------------------------------------------------------------
# Model auto-detection
# ---------------------------------------------------------------------------

# Preferred models in order of preference (cheapest adequate first)
_MODEL_PREFERENCE = [
    "gpt-4o-mini",
    "gpt-4.1-nano",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4.1",
    "gpt-5.4-nano",
    "gpt-5.4-mini",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-3.5-turbo",
]


def auto_detect_model(client: OpenAI) -> str:
    """Pick the best available model from the user's account.

    Prefers cheap, fast models that can handle structured JSON output.
    """
    try:
        available = {m.id for m in client.models.list()}
    except Exception:
        logger.warning("Could not list models; defaulting to gpt-4o-mini")
        return "gpt-4o-mini"

    for model in _MODEL_PREFERENCE:
        if model in available:
            logger.info("Auto-detected model: %s", model)
            return model

    # Last resort — use whatever's available
    logger.warning("No preferred model found; defaulting to gpt-4o-mini")
    return "gpt-4o-mini"


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

class LLMClient:
    """Wraps OpenAI API for media-renamer prompts with structured output."""

    def __init__(self, config: AppConfig) -> None:
        self._client = OpenAI(api_key=config.openai_api_key)
        self._model = config.openai_model or auto_detect_model(self._client)
        logger.info("LLMClient using model: %s", self._model)

    @property
    def model(self) -> str:
        return self._model

    def _chat(self, system: str, user: str) -> str:
        """Send a chat completion request and return the assistant's reply."""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""

    # --- Folder name interpretation -------------------------------------------

    def interpret_folder_name(self, folder_name: str) -> FolderInterpretation:
        """Ask the LLM to parse a MakeMKV disc folder name."""
        system = (
            "You are a media librarian assistant. Your job is to interpret disc folder "
            "names from DVD/Blu-ray rips produced by MakeMKV.\n\n"
            "Given a folder name, extract:\n"
            "- title: the movie or TV show name (properly capitalized)\n"
            "- season: season number (integer) if this is a TV series, null otherwise\n"
            "- disc: disc number (integer) if identifiable, null otherwise\n"
            "- content_type: 'movie', 'tv', or 'unknown'\n"
            "- confidence: 'high', 'medium', or 'low'\n"
            "- notes: any observations about the name (e.g., region codes, unusual formatting)\n\n"
            "Common patterns:\n"
            "- Underscores or missing spaces between words\n"
            "- 'S1', 'S2', 'SEASON ONE' = season indicators\n"
            "- 'D1', 'D2', 'DISC1', 'DISC 1' = disc indicators\n"
            "- Region codes like 'US', 'UK' should be ignored\n"
            "- Disc labels are often ALL CAPS with no spaces\n\n"
            "Respond with valid JSON matching the schema above."
        )
        user = f"Folder name: {folder_name}"

        try:
            raw = self._chat(system, user)
            data = json.loads(raw)
            return FolderInterpretation(
                title=data.get("title", folder_name),
                season=data.get("season"),
                disc=data.get("disc"),
                content_type=data.get("content_type", "unknown"),
                confidence=data.get("confidence", "medium"),
                notes=data.get("notes", ""),
            )
        except Exception:
            logger.exception("LLM folder interpretation failed for %r", folder_name)
            return parse_folder_name_fallback(folder_name)

    # --- Extras classification ------------------------------------------------

    def classify_extra(
        self,
        filename: str,
        duration_minutes: float,
        show_title: str | None = None,
    ) -> ExtraClassification:
        """Ask the LLM to classify a bonus/extra file for Plex naming.

        Plex extra types: behindthescenes, deleted, featurette, interview,
        scene, short, trailer, other.
        """
        system = (
            "You are a media librarian. Classify this bonus/extra file from a "
            "DVD/Blu-ray rip into one of Plex's extra categories.\n\n"
            "Categories:\n"
            "- behindthescenes: behind-the-scenes/making-of content\n"
            "- deleted: deleted or extended scenes\n"
            "- featurette: short documentary or featurette\n"
            "- interview: cast/crew interviews\n"
            "- scene: individual scenes\n"
            "- short: short films\n"
            "- trailer: trailers or teasers\n"
            "- other: anything that doesn't fit above\n\n"
            "Respond with JSON: {\"extra_type\": \"...\", \"label\": \"...\", \"confidence\": \"...\"}\n"
            "- label: a short human-readable description if you can guess what it is, empty string otherwise\n"
            "- confidence: 'high', 'medium', or 'low'"
        )
        context = f"Filename: {filename}\nDuration: {duration_minutes:.1f} minutes"
        if show_title:
            context += f"\nParent title: {show_title}"

        try:
            raw = self._chat(system, context)
            data = json.loads(raw)
            return ExtraClassification(
                extra_type=data.get("extra_type", "other"),
                label=data.get("label", ""),
                confidence=data.get("confidence", "medium"),
            )
        except Exception:
            logger.exception("LLM extra classification failed for %r", filename)
            return ExtraClassification(extra_type="other", confidence="low")


# ---------------------------------------------------------------------------
# Fallback: regex-based folder name parsing (no LLM required)
# ---------------------------------------------------------------------------

# Patterns for season indicators
_SEASON_PATTERNS = [
    r"[_\s]S(\d{1,2})(?:[_\s]|$)",               # S1, S02
    r"SEASON[_\s]*(\d{1,2})",                      # SEASON1, SEASON 02
    r"SEASON[_\s]*(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)",
]

_DISC_PATTERNS = [
    r"[_\s]D(\d{1,2})(?:[_\s]|$)",                 # D1, D02
    r"DISC[_\s]*(\d{1,2})",                         # DISC1, DISC 02
]

_WORD_TO_NUM = {
    "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
    "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10,
}


def parse_folder_name_fallback(folder_name: str) -> FolderInterpretation:
    """Best-effort regex parsing when the LLM is unavailable.

    Handles common MakeMKV disc label patterns but won't catch
    everything — that's what the LLM is for.
    """
    upper = folder_name.upper()
    season: int | None = None
    disc: int | None = None
    content_type = "unknown"

    # --- Extract season ---
    for pattern in _SEASON_PATTERNS:
        m = re.search(pattern, upper)
        if m:
            val = m.group(1)
            season = _WORD_TO_NUM.get(val, None) or int(val)
            content_type = "tv"
            break

    # --- Extract disc ---
    for pattern in _DISC_PATTERNS:
        m = re.search(pattern, upper)
        if m:
            disc = int(m.group(1))
            break

    # --- Extract title ---
    # Remove season/disc indicators and common noise
    title = upper
    for pattern in _SEASON_PATTERNS + _DISC_PATTERNS:
        title = re.sub(pattern, " ", title)
    # Remove region codes
    title = re.sub(r"\b(US|UK|EU|PAL|NTSC)\b", "", title)
    # Replace underscores with spaces, collapse whitespace
    title = title.replace("_", " ")
    title = re.sub(r"\s+", " ", title).strip()
    # Title-case the result
    title = title.title() if title else folder_name

    return FolderInterpretation(
        title=title,
        season=season,
        disc=disc,
        content_type=content_type,
        confidence="low",
        notes="Parsed with regex fallback (no LLM)",
    )
