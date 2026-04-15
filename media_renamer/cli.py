"""CLI entry point for Media Renamer — powered by Typer."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from media_renamer import __version__
from media_renamer.config import AppConfig, load_config
from media_renamer.identifier import TMDbClient, classify_content_type
from media_renamer.grouper import DiscGroup, group_tv_discs
from media_renamer.matcher import (
    compute_disc_episode_offset,
    estimate_episodes_per_disc,
    match_episodes_by_duration,
    match_movie,
    reclassify_unmatched,
)
from media_renamer.models import (
    ContentType,
    DiscFolder,
    EpisodeMatch,
    FileClassification,
    MatchConfidence,
    MediaFile,
    MovieMatch,
    ProcessingResult,
    TVShowMatch,
)
from media_renamer.prompts import LLMClient, FolderInterpretation, parse_folder_name_fallback
from media_renamer.renamer import (
    build_movie_dest,
    build_movie_extra_dest,
    build_tv_episode_dest,
    build_tv_extra_dest,
    execute_movie_moves,
    execute_tv_moves,
    write_processing_log,
)
from media_renamer.scanner import classify_disc_files, scan_source_directory
from media_renamer.ui import (
    SessionStats,
    UserAction,
    display_batch_disc_result,
    display_batch_group_summary,
    display_movie_match,
    display_output_paths,
    display_scan_summary,
    display_session_summary,
    display_tv_match,
    prompt_confirm_batch,
    prompt_confirm_mapping,
    prompt_edit_movie,
    prompt_edit_tv_show,
    prompt_handle_unmatched,
    prompt_select_episodes_to_edit,
    prompt_tmdb_search_results,
)

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="media-renamer",
    help="Identify and rename MakeMKV output into a Plex-ready folder structure.",
    add_completion=False,
)

console = Console()


# ---------------------------------------------------------------------------
# Plex path builders (preview only — actual moves use renamer.py)
# ---------------------------------------------------------------------------

def _tv_episode_path(
    show: TVShowMatch,
    ep: EpisodeMatch,
    dest_root: Path | None = None,
) -> str:
    """Build a Plex-relative path for a TV episode (for display)."""
    if dest_root:
        return str(build_tv_episode_dest(dest_root, show, ep))
    year_str = f" ({show.year})" if show.year else ""
    tvdb_str = f" {{tvdb-{show.tvdb_id}}}" if show.tvdb_id else ""
    show_dir = f"{show.title}{year_str}{tvdb_str}"
    season_dir = f"Season {ep.episode.season_number:02d}"
    ep_file = (
        f"{show.title}{year_str} - "
        f"s{ep.episode.season_number:02d}e{ep.episode.episode_number:02d} - "
        f"{ep.episode.title}.mkv"
    )
    return f"TV Shows/{show_dir}/{season_dir}/{ep_file}"


def _movie_path(movie: MovieMatch, dest_root: Path | None = None) -> str:
    """Build a Plex-relative path for a movie (for display)."""
    if dest_root:
        return str(build_movie_dest(dest_root, movie))
    year_str = f" ({movie.year})" if movie.year else ""
    imdb_str = f" {{imdb-{movie.imdb_id}}}" if movie.imdb_id else ""
    movie_dir = f"{movie.title}{year_str}{imdb_str}"
    return f"Movies/{movie_dir}/{movie_dir}.mkv"


def _tv_extra_path(show: TVShowMatch, filename: str) -> str:
    """Build a Plex-relative path for a TV extra/featurette (for display)."""
    year_str = f" ({show.year})" if show.year else ""
    tvdb_str = f" {{tvdb-{show.tvdb_id}}}" if show.tvdb_id else ""
    show_dir = f"{show.title}{year_str}{tvdb_str}"
    return f"TV Shows/{show_dir}/Featurettes/{filename}"


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

def _init_llm(cfg: AppConfig) -> LLMClient | None:
    """Initialize the LLM client, returning None if no API key."""
    if not cfg.openai_api_key:
        console.print("  [dim]No OpenAI API key — using regex fallback for folder names[/dim]")
        return None
    try:
        client = LLMClient(cfg)
        console.print(f"  [dim]LLM model: {client.model}[/dim]")
        return client
    except Exception as e:
        console.print(f"  [dim]LLM init failed ({e}) — using regex fallback[/dim]")
        return None


def _interpret_folder(
    name: str,
    llm: LLMClient | None,
) -> FolderInterpretation:
    """Interpret a folder name via LLM or regex fallback."""
    if llm:
        return llm.interpret_folder_name(name)
    return parse_folder_name_fallback(name)


def _search_tmdb_tv(
    tmdb: TMDbClient,
    interp: FolderInterpretation,
) -> TVShowMatch | None:
    """Search TMDb for a TV show and let user confirm."""
    results = tmdb.search_tv(interp.title)
    if not results:
        console.print(f"  [yellow]No TMDb results for \"{interp.title}\"[/yellow]")
        return None

    result_dicts = [
        {"tmdb_id": r.tmdb_id, "title": r.title, "first_air_year": r.first_air_year}
        for r in results
    ]
    chosen_id = prompt_tmdb_search_results(result_dicts, "tv")
    if chosen_id is None:
        return None

    season = interp.season or 1
    return tmdb.build_tv_match(chosen_id, season)


def _search_tmdb_movie(
    tmdb: TMDbClient,
    interp: FolderInterpretation,
) -> MovieMatch | None:
    """Search TMDb for a movie and let user confirm."""
    results = tmdb.search_movie(interp.title)
    if not results:
        console.print(f"  [yellow]No TMDb results for \"{interp.title}\"[/yellow]")
        return None

    result_dicts = [
        {"tmdb_id": r.tmdb_id, "title": r.title, "year": r.year}
        for r in results
    ]
    chosen_id = prompt_tmdb_search_results(result_dicts, "movie")
    if chosen_id is None:
        return None

    return tmdb.get_movie_details(chosen_id)


def _parse_disc_number(folder_name: str) -> int:
    """Extract disc number from a folder name."""
    upper = folder_name.upper()
    m = re.search(r"D(\d+)|DISC\s*(\d+)", upper)
    if m:
        return int(m.group(1) or m.group(2))
    return 1


# ---------------------------------------------------------------------------
# Batch TV processing (Phase 9)
# ---------------------------------------------------------------------------

def _process_tv_batch(
    group: DiscGroup,
    tmdb: TMDbClient,
    cfg: AppConfig,
    stats: SessionStats,
    all_results: list,
) -> None:
    """Process an entire TV disc group: single TMDb lookup, cascading offsets.

    1. Search TMDb once for the group
    2. Confirm with user once
    3. Process each disc sequentially — disc N starts at the offset
       where disc N-1 left off
    4. Display per-disc results (read-only, no prompts)
    """
    # Search TMDb once using the group's title + season
    interp_for_search = group.sorted_discs()[0][1]
    show = _search_tmdb_tv(tmdb, interp_for_search)
    if not show:
        stats.folders_skipped += group.disc_count
        console.print(f"  [dim]Skipped group \"{group.title}\" S{group.season:02d} — no TMDb match.[/dim]\n")
        return

    season_num = show.season_number or group.season
    episodes = tmdb.get_season_episodes(show.tmdb_id, season_num)
    if not episodes:
        console.print(f"  [red]Could not fetch episodes for {show.title} season {season_num}[/red]")
        stats.errors.append(f"{group.title} S{group.season}: no episodes")
        return

    console.print(f"\n  [bold]{show.title} ({show.year}) — Season {season_num}[/bold]")
    console.print(f"  [dim]{len(episodes)} episode(s) across {group.disc_count} disc(s)[/dim]\n")

    # Confirm batch processing
    action = prompt_confirm_batch(show.title, season_num, group.disc_count)
    if action == UserAction.SKIP:
        stats.folders_skipped += group.disc_count
        console.print("  [dim]⏭️  Skipped group.[/dim]\n")
        return

    # Process each disc with cascading offsets
    next_offset = 0
    for disc, interp in group.sorted_discs():
        try:
            matched_count, extras_count, skipped_count, error_count = _process_tv_disc_batch(
                disc, show, episodes, cfg, stats, all_results,
                episode_offset=next_offset,
            )
            # Cascade: next disc starts where this one left off
            next_offset += matched_count

            display_batch_disc_result(
                disc.name, matched_count, skipped_count, extras_count,
                error_count=error_count, dry_run=cfg.dry_run,
            )
        except Exception as e:
            logger.exception("Error processing %s in batch", disc.name)
            stats.errors.append(f"{disc.name}: {e}")
            console.print(f"  [red]❌ {disc.name}: {e}[/red]")

    if cfg.dry_run:
        console.print(f"\n  [bold yellow]📋 DRY RUN — nothing moved for this group.[/bold yellow]\n")
    else:
        console.print()


def _process_tv_disc_batch(
    disc: DiscFolder,
    show: TVShowMatch,
    episodes: list,
    cfg: AppConfig,
    stats: SessionStats,
    all_results: list,
    episode_offset: int = 0,
) -> tuple[int, int, int, int]:
    """Process a single TV disc in batch mode (non-interactive).

    Returns (matched_count, extras_count, skipped_count, error_count).
    """
    classified = classify_disc_files(disc, cfg)
    sorted_files = sorted(classified.files, key=lambda f: f.filename)

    matched, _ = match_episodes_by_duration(
        sorted_files, episodes, cfg, episode_offset=episode_offset,
    )

    matched_names = {m.file.filename for m in matched}
    reclassified = reclassify_unmatched(sorted_files, matched_names, cfg)

    play_all_files = [
        f for f in reclassified
        if f.classification == FileClassification.PLAY_ALL
        and f.filename not in matched_names
    ]
    bonus_files = [
        f for f in reclassified
        if f.classification == FileClassification.BONUS
        and f.filename not in matched_names
    ]

    result = execute_tv_moves(
        dest_root=cfg.dest_dir,
        show=show,
        matched=matched,
        extras=bonus_files,
        skipped=play_all_files,
        dry_run=cfg.dry_run,
    )
    all_results.append(result)

    stats.episodes_matched += len(matched)
    stats.play_all_skipped += len(play_all_files)
    stats.extras_found += len(bonus_files)
    stats.files_moved += result.moved_count
    stats.folders_processed += 1

    return len(matched), len(bonus_files), len(play_all_files), result.error_count


# ---------------------------------------------------------------------------
# Per-folder interactive processing (existing)
# ---------------------------------------------------------------------------


def _process_tv_folder(
    disc: DiscFolder,
    show: TVShowMatch,
    tmdb: TMDbClient,
    cfg: AppConfig,
    stats: SessionStats,
    interp: FolderInterpretation,
    all_results: list,
    season_disc_count: int = 1,
) -> None:
    """Process a single TV disc folder: match, display, confirm, move."""
    season_num = show.season_number or interp.season or 1
    episodes = tmdb.get_season_episodes(show.tmdb_id, season_num)

    if not episodes:
        console.print(f"  [red]Could not fetch episodes for season {season_num}[/red]")
        stats.errors.append(f"{disc.name}: no episodes for season {season_num}")
        return

    # Classify and sort files
    classified = classify_disc_files(disc, cfg)
    sorted_files = sorted(classified.files, key=lambda f: f.filename)

    # Compute episode offset using season-level disc count
    disc_num = interp.disc or _parse_disc_number(disc.name)
    eps_per_disc = estimate_episodes_per_disc(len(episodes), season_disc_count)
    offset = compute_disc_episode_offset(disc_num, eps_per_disc, len(episodes))

    # Match episodes by duration
    matched, unmatched_files = match_episodes_by_duration(
        sorted_files, episodes, cfg, episode_offset=offset,
    )

    # Reclassify unmatched files
    matched_names = {m.file.filename for m in matched}
    reclassified = reclassify_unmatched(sorted_files, matched_names, cfg)

    # Separate skipped files (play_all, bonus)
    skipped = [
        f for f in reclassified
        if f.classification in (FileClassification.PLAY_ALL, FileClassification.BONUS)
        and f.filename not in matched_names
    ]
    unknown = [
        f for f in reclassified
        if f.classification == FileClassification.UNKNOWN
        and f.filename not in matched_names
    ]

    # Display the match table
    display_tv_match(disc.name, show, matched, unknown, skipped, dry_run=cfg.dry_run)

    # Show proposed output paths
    paths = [
        (em.file.filename, _tv_episode_path(show, em))
        for em in matched
    ]
    if paths:
        display_output_paths(paths)

    # Interactive confirm/edit/skip loop
    while True:
        action = prompt_confirm_mapping()

        if action == UserAction.CONFIRM:
            # Decide which extras to keep
            extras_to_move: list[MediaFile] = []
            bonus_files = [f for f in skipped if f.classification == FileClassification.BONUS]

            if unknown:
                decisions = prompt_handle_unmatched(unknown, show.title)
                for f, decision in decisions:
                    if decision == "keep_as_extra":
                        extras_to_move.append(f)

            # Include bonus files as extras
            extras_to_move.extend(bonus_files)

            play_all_files = [f for f in skipped if f.classification == FileClassification.PLAY_ALL]

            # Execute file moves
            result = execute_tv_moves(
                dest_root=cfg.dest_dir,
                show=show,
                matched=matched,
                extras=extras_to_move,
                skipped=play_all_files,
                dry_run=cfg.dry_run,
            )
            all_results.append(result)

            # Update stats
            stats.episodes_matched += len(matched)
            stats.play_all_skipped += len(play_all_files)
            stats.extras_found += len(extras_to_move)
            stats.files_moved += result.moved_count
            stats.folders_processed += 1

            if cfg.dry_run:
                console.print("  [bold yellow]📋 DRY RUN — nothing moved.[/bold yellow]\n")
            else:
                console.print(
                    f"  [bold green]✅ Moved {result.moved_count} file(s).[/bold green]"
                )
                if result.error_count:
                    console.print(f"  [bold red]⚠️  {result.error_count} error(s) during move.[/bold red]")
                console.print()
            break

        elif action == UserAction.EDIT:
            old_show = show
            show = prompt_edit_tv_show(show)

            # If the show or season changed, refetch episodes and rematch
            if (show.tmdb_id != old_show.tmdb_id
                    or show.season_number != old_show.season_number):
                new_season = show.season_number or 1
                new_episodes = tmdb.get_season_episodes(show.tmdb_id, new_season)
                if new_episodes:
                    episodes = new_episodes
                    new_eps_per_disc = estimate_episodes_per_disc(len(episodes), season_disc_count)
                    new_offset = compute_disc_episode_offset(disc_num, new_eps_per_disc, len(episodes))
                    matched, unmatched_files = match_episodes_by_duration(
                        sorted_files, episodes, cfg, episode_offset=new_offset,
                    )
                    matched_names = {m.file.filename for m in matched}
                    reclassified = reclassify_unmatched(sorted_files, matched_names, cfg)
                    skipped = [
                        f for f in reclassified
                        if f.classification in (FileClassification.PLAY_ALL, FileClassification.BONUS)
                        and f.filename not in matched_names
                    ]
                    unknown = [
                        f for f in reclassified
                        if f.classification == FileClassification.UNKNOWN
                        and f.filename not in matched_names
                    ]
                else:
                    console.print(f"  [red]Could not fetch episodes for new season {new_season} — reverting edit[/red]")
                    show = old_show
            else:
                matched = prompt_select_episodes_to_edit(matched)

            display_tv_match(disc.name, show, matched, unknown, skipped, dry_run=cfg.dry_run)
            paths = [(em.file.filename, _tv_episode_path(show, em)) for em in matched]
            if paths:
                display_output_paths(paths)

        elif action == UserAction.SKIP:
            stats.folders_skipped += 1
            console.print("  [dim]⏭️  Skipped.[/dim]\n")
            break


def _process_movie_folder(
    disc: DiscFolder,
    movie: MovieMatch,
    cfg: AppConfig,
    stats: SessionStats,
    all_results: list,
) -> None:
    """Process a single movie disc folder: match, display, confirm, move."""
    classified = classify_disc_files(disc, cfg)
    sorted_files = sorted(classified.files, key=lambda f: f.filename)

    main_file, confidence, extras = match_movie(sorted_files, movie, cfg)

    display_movie_match(disc.name, movie, main_file, confidence, extras, dry_run=cfg.dry_run)

    if main_file:
        display_output_paths([(main_file.filename, _movie_path(movie))])

    while True:
        action = prompt_confirm_mapping()

        if action == UserAction.CONFIRM:
            # Execute file moves
            result = execute_movie_moves(
                dest_root=cfg.dest_dir,
                movie=movie,
                main_file=main_file,
                extras=extras,
                dry_run=cfg.dry_run,
            )
            all_results.append(result)

            # Update stats
            if main_file:
                stats.movies_matched += 1
            stats.extras_found += len([e for e in extras if e.classification == FileClassification.BONUS])
            stats.play_all_skipped += len([e for e in extras if e.classification == FileClassification.PLAY_ALL])
            stats.files_moved += result.moved_count
            stats.folders_processed += 1

            if cfg.dry_run:
                console.print("  [bold yellow]📋 DRY RUN — nothing moved.[/bold yellow]\n")
            else:
                console.print(
                    f"  [bold green]✅ Moved {result.moved_count} file(s).[/bold green]"
                )
                if result.error_count:
                    console.print(f"  [bold red]⚠️  {result.error_count} error(s) during move.[/bold red]")
                console.print()
            break

        elif action == UserAction.EDIT:
            movie = prompt_edit_movie(movie)
            display_movie_match(disc.name, movie, main_file, confidence, extras, dry_run=cfg.dry_run)
            if main_file:
                display_output_paths([(main_file.filename, _movie_path(movie))])

        elif action == UserAction.SKIP:
            stats.folders_skipped += 1
            console.print("  [dim]⏭️  Skipped.[/dim]\n")
            break


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

@app.command()
def main(
    source: Annotated[
        Path,
        typer.Option(
            "--source", "-s",
            help="Source directory containing MakeMKV output folders.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    dest: Annotated[
        Path,
        typer.Option(
            "--dest", "-d",
            help="Destination/staging directory for Plex-ready output.",
            resolve_path=True,
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview actions without moving or renaming any files.",
        ),
    ] = False,
    config_file: Annotated[
        Optional[Path],
        typer.Option(
            "--config", "-c",
            help="Path to config.yaml (default: ./config.yaml).",
        ),
    ] = None,
    env_file: Annotated[
        Optional[Path],
        typer.Option(
            "--env-file",
            help="Path to .env file (default: auto-detect).",
        ),
    ] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-v",
            help="Show version and exit.",
            is_eager=True,
        ),
    ] = False,
    no_batch: Annotated[
        bool,
        typer.Option(
            "--no-batch",
            help="Disable auto-grouping of TV disc folders (process each folder individually).",
        ),
    ] = False,
) -> None:
    """Scan MakeMKV output, identify content, and rename into Plex format."""
    if version:
        console.print(f"media-renamer v{__version__}")
        raise typer.Exit()

    # Build configuration
    cfg = load_config(
        env_file=env_file,
        config_file=config_file,
        source_dir=source,
        dest_dir=dest,
        dry_run=dry_run,
    )

    # Banner
    from rich.panel import Panel
    mode_label = "[bold yellow]DRY RUN[/bold yellow]" if cfg.dry_run else "[bold green]LIVE[/bold green]"
    console.print(
        Panel(
            f"[bold]Media Renamer[/bold] v{__version__}  •  {mode_label}\n"
            f"Source: {cfg.source_dir}\n"
            f"Dest:   {cfg.dest_dir}",
            title="🎬 Media Renamer",
            expand=False,
        )
    )

    # Ensure destination directory exists
    if cfg.dest_dir and not cfg.dest_dir.exists():
        if not cfg.dry_run:
            cfg.dest_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[dim]Created destination directory: {cfg.dest_dir}[/dim]")
        else:
            console.print(f"[dim]Would create destination directory: {cfg.dest_dir}[/dim]")

    # ── Phase 1: Initialize services ──
    llm = _init_llm(cfg)

    if not cfg.tmdb_api_key:
        console.print("[bold red]Error: TMDB_API_KEY not set. See .env.example.[/bold red]")
        raise typer.Exit(code=1)

    tmdb = TMDbClient(cfg.tmdb_api_key)

    # ── Phase 2: Scan ──
    console.print("\n[bold]Scanning source directory...[/bold]")
    discs = scan_source_directory(source)
    if not discs:
        console.print("[yellow]No MKV folders found in source directory.[/yellow]")
        raise typer.Exit()

    discs.sort(key=lambda d: d.name)
    display_scan_summary([d.name for d in discs])

    # ── Process each folder ──
    stats = SessionStats()
    all_results: list[ProcessingResult] = []

    # Pre-interpret all folder names
    interpretations: list[FolderInterpretation] = []
    for disc in discs:
        interp = _interpret_folder(disc.name, llm)
        interpretations.append(interp)
        console.print(f"  [dim]Interpreted: \"{interp.title}\" type={interp.content_type} "
                       f"season={interp.season} disc={interp.disc} "
                       f"(confidence={interp.confidence})[/dim]")

    # ── Batch grouping ──
    if not no_batch:
        groups, ungrouped = group_tv_discs(discs, interpretations)
    else:
        groups = []
        ungrouped = list(zip(discs, interpretations))

    if groups:
        display_batch_group_summary(groups, ungrouped)

    # Process grouped TV discs (batch mode — single confirm per group)
    for group in groups:
        try:
            _process_tv_batch(group, tmdb, cfg, stats, all_results)
        except KeyboardInterrupt:
            console.print("\n[bold red]Interrupted by user.[/bold red]")
            break
        except Exception as e:
            logger.exception("Error processing group %s S%d", group.title, group.season)
            stats.errors.append(f"{group.title} S{group.season}: {e}")
            console.print(f"  [bold red]Error: {e}[/bold red]\n")

    # Process ungrouped folders individually (existing interactive flow)
    # Compute disc counts for ungrouped TV folders (fallback offset estimation)
    from collections import Counter
    season_disc_counts: Counter[tuple[str, int]] = Counter()
    for _, interp in ungrouped:
        season = interp.season or 1
        key = (interp.title.lower().strip(), season)
        season_disc_counts[key] += 1

    for disc, interp in ungrouped:
        # 2. Classify files to determine content type heuristic
        classified = classify_disc_files(disc, cfg)
        content_type = classify_content_type(classified, cfg)

        # Use LLM's content type if available and confident
        if interp.content_type == "tv":
            content_type = ContentType.TV_SERIES
        elif interp.content_type == "movie":
            content_type = ContentType.MOVIE

        # 3. Search TMDb and process based on content type
        disc_count_key = (interp.title.lower().strip(), interp.season or 1)
        sdc = season_disc_counts.get(disc_count_key, 1)

        try:
            if content_type == ContentType.TV_SERIES:
                show = _search_tmdb_tv(tmdb, interp)
                if show:
                    _process_tv_folder(disc, show, tmdb, cfg, stats, interp, all_results, season_disc_count=sdc)
                else:
                    stats.folders_skipped += 1
                    console.print(f"  [dim]Skipped {disc.name} — no TMDb match.[/dim]\n")

            elif content_type == ContentType.MOVIE:
                movie = _search_tmdb_movie(tmdb, interp)
                if movie:
                    _process_movie_folder(disc, movie, cfg, stats, all_results)
                else:
                    stats.folders_skipped += 1
                    console.print(f"  [dim]Skipped {disc.name} — no TMDb match.[/dim]\n")

            else:
                # Unknown content type — ask user
                console.print(f"\n  [yellow]Could not determine content type for: {disc.name}[/yellow]")
                import questionary
                ct_choice = questionary.select(
                    "What type of content is this?",
                    choices=["TV Series", "Movie", "Skip"],
                ).ask()
                if ct_choice == "TV Series":
                    show = _search_tmdb_tv(tmdb, interp)
                    if show:
                        _process_tv_folder(disc, show, tmdb, cfg, stats, interp, all_results, season_disc_count=sdc)
                elif ct_choice == "Movie":
                    movie = _search_tmdb_movie(tmdb, interp)
                    if movie:
                        _process_movie_folder(disc, movie, cfg, stats, all_results)
                else:
                    stats.folders_skipped += 1
                    console.print(f"  [dim]Skipped {disc.name}.[/dim]\n")

        except KeyboardInterrupt:
            console.print("\n[bold red]Interrupted by user.[/bold red]")
            break
        except Exception as e:
            logger.exception("Error processing %s", disc.name)
            stats.errors.append(f"{disc.name}: {e}")
            console.print(f"  [bold red]Error: {e}[/bold red]\n")

    # ── Processing log ──
    if all_results and cfg.dest_dir:
        log_path = write_processing_log(cfg.dest_dir, all_results, dry_run=cfg.dry_run)
        if not cfg.dry_run:
            console.print(f"  📝 Log saved to: {log_path}")

    # ── Session summary ──
    display_session_summary(stats, dry_run=cfg.dry_run)


if __name__ == "__main__":
    app()
