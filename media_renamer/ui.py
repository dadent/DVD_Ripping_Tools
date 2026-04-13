"""Interactive terminal UI — Rich display and questionary prompts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import questionary
from questionary import Style

from media_renamer.models import (
    ContentType,
    EpisodeMatch,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
    TVShowMatch,
)

logger = logging.getLogger(__name__)

console = Console()

# questionary theme
_STYLE = Style([
    ("qmark", "fg:cyan bold"),
    ("question", "bold"),
    ("answer", "fg:green bold"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan bold"),
    ("selected", "fg:green"),
])


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_duration(seconds: float) -> str:
    """Format seconds as H:MM:SS or M:SS."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_confidence(conf: MatchConfidence) -> str:
    """Return a coloured confidence badge for Rich."""
    if conf == MatchConfidence.HIGH:
        return "[bold green]HIGH[/bold green]"
    elif conf == MatchConfidence.MEDIUM:
        return "[bold yellow]MED[/bold yellow]"
    else:
        return "[bold red]LOW[/bold red]"


def _classification_icon(cls: FileClassification) -> str:
    icons = {
        FileClassification.EPISODE: "📺",
        FileClassification.MAIN_FEATURE: "🎬",
        FileClassification.PLAY_ALL: "⏭️",
        FileClassification.BONUS: "📦",
        FileClassification.UNKNOWN: "❓",
    }
    return icons.get(cls, "❓")


# ---------------------------------------------------------------------------
# Folder discovery summary
# ---------------------------------------------------------------------------

def display_scan_summary(folder_names: list[str]) -> None:
    """Show the list of discovered folders after scanning."""
    console.print(f"\nFound [bold cyan]{len(folder_names)}[/bold cyan] folder(s) to process:\n")
    for i, name in enumerate(folder_names, 1):
        console.print(f"  {i}. {name}")
    console.print()


# ---------------------------------------------------------------------------
# TV show file table
# ---------------------------------------------------------------------------

def display_tv_match(
    folder_name: str,
    show: TVShowMatch,
    matched: list[EpisodeMatch],
    unmatched: list[MediaFile],
    skipped: list[MediaFile],
    dry_run: bool = False,
) -> None:
    """Display the proposed TV episode mapping for a disc folder."""
    console.rule(f"[bold]Processing: {folder_name}[/bold]")

    # Header info
    tvdb_str = f"TVDB: {show.tvdb_id}" if show.tvdb_id else "TVDB: —"
    year_str = f" ({show.year})" if show.year else ""
    console.print(
        f"\n  🤖 AI Analysis: [bold]\"{show.title}\"{year_str}[/bold] — "
        f"Season {show.season_number} — TV Series"
    )
    console.print(f"  📊 {tvdb_str} | TMDb: {show.tmdb_id}")
    if dry_run:
        console.print("  [bold yellow]📋 DRY RUN — no files will be moved[/bold yellow]")
    console.print()

    # File table
    table = Table(show_header=True, header_style="bold", expand=False, pad_edge=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Source File", max_width=45, no_wrap=True)
    table.add_column("Duration", justify="right", width=9)
    table.add_column("Proposed Match", min_width=35)
    table.add_column("Conf", justify="center", width=6)

    # Matched episodes
    for i, em in enumerate(matched, 1):
        ep = em.episode
        table.add_row(
            str(i),
            em.file.filename,
            format_duration(em.file.duration_seconds),
            f"s{ep.season_number:02d}e{ep.episode_number:02d} - {ep.title}",
            format_confidence(em.confidence),
        )

    # Unmatched files (unknown classification)
    for uf in unmatched:
        table.add_row(
            "—",
            uf.filename,
            format_duration(uf.duration_seconds),
            f"{_classification_icon(uf.classification)} Unmatched ({uf.classification.value})",
            "",
        )

    # Skipped files (play_all, bonus)
    for sf in skipped:
        label = "Play All (skip)" if sf.classification == FileClassification.PLAY_ALL else "Extra"
        table.add_row(
            "—",
            sf.filename,
            format_duration(sf.duration_seconds),
            f"{_classification_icon(sf.classification)} {label}",
            "",
            style="dim",
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Movie file table
# ---------------------------------------------------------------------------

def display_movie_match(
    folder_name: str,
    movie: MovieMatch,
    main_file: MediaFile | None,
    main_confidence: MatchConfidence,
    extras: list[MediaFile],
    dry_run: bool = False,
) -> None:
    """Display the proposed movie mapping for a disc folder."""
    console.rule(f"[bold]Processing: {folder_name}[/bold]")

    year_str = f" ({movie.year})" if movie.year else ""
    imdb_str = f"IMDB: {movie.imdb_id}" if movie.imdb_id else "IMDB: —"
    console.print(
        f"\n  🤖 AI Analysis: [bold]\"{movie.title}\"{year_str}[/bold] — Movie"
    )
    console.print(f"  📊 {imdb_str} | TMDb: {movie.tmdb_id}")
    if dry_run:
        console.print("  [bold yellow]📋 DRY RUN — no files will be moved[/bold yellow]")
    console.print()

    table = Table(show_header=True, header_style="bold", expand=False, pad_edge=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Source File", max_width=45, no_wrap=True)
    table.add_column("Duration", justify="right", width=9)
    table.add_column("Proposed Match", min_width=30)
    table.add_column("Conf", justify="center", width=6)

    if main_file:
        table.add_row(
            "1",
            main_file.filename,
            format_duration(main_file.duration_seconds),
            "✅ Main Feature",
            format_confidence(main_confidence),
        )

    for i, ex in enumerate(extras, 2 if main_file else 1):
        icon = _classification_icon(ex.classification)
        table.add_row(
            str(i),
            ex.filename,
            format_duration(ex.duration_seconds),
            f"{icon} Extra",
            "",
            style="dim" if ex.classification in (FileClassification.BONUS, FileClassification.PLAY_ALL) else "",
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Plex path preview
# ---------------------------------------------------------------------------

def display_output_paths(paths: list[tuple[str, str]]) -> None:
    """Show source → destination path mappings.

    *paths* is a list of (source_filename, dest_relative_path) tuples.
    """
    console.print("  [bold]Output paths:[/bold]")
    for src, dst in paths:
        console.print(f"    {src}  →  [green]{dst}[/green]")
    console.print()


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

class UserAction:
    """Constants for user action choices."""
    CONFIRM = "confirm"
    EDIT = "edit"
    SKIP = "skip"


def prompt_confirm_mapping() -> str:
    """Ask user to Confirm, Edit, or Skip the proposed mapping."""
    choice = questionary.select(
        "Accept this mapping?",
        choices=[
            questionary.Choice("✅ Confirm", value=UserAction.CONFIRM),
            questionary.Choice("✏️  Edit", value=UserAction.EDIT),
            questionary.Choice("⏭️  Skip", value=UserAction.SKIP),
        ],
        style=_STYLE,
    ).ask()
    return choice or UserAction.SKIP


def prompt_edit_tv_show(show: TVShowMatch) -> TVShowMatch:
    """Let the user edit the TV show title, season, or TVDB ID."""
    console.print("\n  [bold]Edit TV Show Details:[/bold]")

    new_title = questionary.text(
        "Title:",
        default=show.title,
        style=_STYLE,
    ).ask()

    new_season = questionary.text(
        "Season number:",
        default=str(show.season_number or ""),
        style=_STYLE,
    ).ask()

    new_tvdb = questionary.text(
        "TVDB ID (leave blank to keep):",
        default=str(show.tvdb_id or ""),
        style=_STYLE,
    ).ask()

    season_num = None
    if new_season:
        try:
            season_num = int(new_season)
        except ValueError:
            season_num = show.season_number

    tvdb_id = show.tvdb_id
    if new_tvdb:
        try:
            tvdb_id = int(new_tvdb)
        except ValueError:
            pass

    return show.model_copy(update={
        "title": new_title or show.title,
        "season_number": season_num,
        "tvdb_id": tvdb_id,
    })


def prompt_edit_movie(movie: MovieMatch) -> MovieMatch:
    """Let the user edit the movie title, year, or IMDB ID."""
    console.print("\n  [bold]Edit Movie Details:[/bold]")

    new_title = questionary.text(
        "Title:",
        default=movie.title,
        style=_STYLE,
    ).ask()

    new_year = questionary.text(
        "Year:",
        default=str(movie.year or ""),
        style=_STYLE,
    ).ask()

    new_imdb = questionary.text(
        "IMDB ID (e.g., tt0133093):",
        default=movie.imdb_id or "",
        style=_STYLE,
    ).ask()

    year = movie.year
    if new_year:
        try:
            year = int(new_year)
        except ValueError:
            pass

    return movie.model_copy(update={
        "title": new_title or movie.title,
        "year": year,
        "imdb_id": new_imdb or movie.imdb_id,
    })


def prompt_edit_episode(em: EpisodeMatch) -> EpisodeMatch:
    """Let the user change the episode number for a single file."""
    new_ep = questionary.text(
        f"Episode number for {em.file.filename}:",
        default=str(em.episode.episode_number),
        style=_STYLE,
    ).ask()

    try:
        ep_num = int(new_ep)
    except (ValueError, TypeError):
        return em

    return em.model_copy(update={
        "episode": em.episode.model_copy(update={"episode_number": ep_num}),
    })


def prompt_select_episodes_to_edit(matches: list[EpisodeMatch]) -> list[EpisodeMatch]:
    """Let user pick which episode mappings to edit, then edit them."""
    choices = [
        questionary.Choice(
            f"{em.file.filename} → s{em.episode.season_number:02d}e{em.episode.episode_number:02d}",
            value=i,
        )
        for i, em in enumerate(matches)
    ]

    selected = questionary.checkbox(
        "Select episodes to edit:",
        choices=choices,
        style=_STYLE,
    ).ask()

    if not selected:
        return matches

    result = list(matches)
    for idx in selected:
        result[idx] = prompt_edit_episode(result[idx])
    return result


def prompt_handle_unmatched(
    files: list[MediaFile],
    show_title: str | None = None,
) -> list[tuple[MediaFile, str]]:
    """Ask the user what to do with unmatched files.

    Returns list of (file, action) where action is 'skip' or 'keep_as_extra'.
    """
    if not files:
        return []

    console.print("\n  [bold yellow]Unmatched files need your attention:[/bold yellow]")
    results: list[tuple[MediaFile, str]] = []

    for f in files:
        console.print(f"    {f.filename} ({format_duration(f.duration_seconds)})")
        choice = questionary.select(
            f"  What should I do with {f.filename}?",
            choices=[
                questionary.Choice("📦 Keep as extra/featurette", value="keep_as_extra"),
                questionary.Choice("⏭️  Skip (don't move)", value="skip"),
            ],
            style=_STYLE,
        ).ask()
        results.append((f, choice or "skip"))

    return results


def prompt_tmdb_search_results(
    results: list[dict],
    content_type: str,
) -> int | None:
    """Present TMDb search results and let the user pick one.

    *results* should be a list of dicts with 'tmdb_id', 'title', 'year'/'first_air_year'.
    Returns the chosen tmdb_id, or None if user skips.
    """
    if not results:
        console.print("  [bold red]No TMDb results found.[/bold red]")
        return None

    choices = []
    for r in results[:10]:  # cap at 10
        year = r.get("year") or r.get("first_air_year") or "?"
        choices.append(questionary.Choice(
            f"{r['title']} ({year})",
            value=r["tmdb_id"],
        ))
    choices.append(questionary.Choice("⏭️  None of these / Skip", value=None))

    selected = questionary.select(
        "Which is the correct match?",
        choices=choices,
        style=_STYLE,
    ).ask()
    return selected


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------

@dataclass
class SessionStats:
    """Accumulates processing stats across all folders."""
    folders_processed: int = 0
    folders_skipped: int = 0
    episodes_matched: int = 0
    movies_matched: int = 0
    extras_found: int = 0
    play_all_skipped: int = 0
    files_moved: int = 0
    errors: list[str] = field(default_factory=list)


def display_session_summary(stats: SessionStats, dry_run: bool = False) -> None:
    """Show the final session summary."""
    console.print()
    console.rule("[bold]Session Complete[/bold]")

    lines: list[str] = []
    if stats.movies_matched:
        lines.append(f"  🎬 {stats.movies_matched} movie(s) processed")
    if stats.episodes_matched:
        lines.append(f"  📺 {stats.episodes_matched} TV episode(s) matched")
    if stats.extras_found:
        lines.append(f"  📦 {stats.extras_found} extra(s) organized")
    if stats.play_all_skipped:
        lines.append(f"  ⏭️  {stats.play_all_skipped} Play All track(s) skipped")
    if stats.folders_skipped:
        lines.append(f"  ⏩ {stats.folders_skipped} folder(s) skipped")
    if stats.files_moved and not dry_run:
        lines.append(f"  ✅ {stats.files_moved} file(s) moved")
    if dry_run:
        lines.append(f"  📋 [bold yellow]DRY RUN — no files were moved[/bold yellow]")
    if stats.errors:
        lines.append(f"  ❌ {len(stats.errors)} error(s):")
        for err in stats.errors:
            lines.append(f"     • {err}")

    if not lines:
        lines.append("  [dim]Nothing was processed.[/dim]")

    console.print("\n".join(lines))
    console.print()
