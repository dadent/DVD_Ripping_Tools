# Media Renamer — Product Requirements Document (PRD)

## 1. Overview

**Product Name:** Media Renamer
**Type:** Command-line tool (Python core with PowerShell wrapper)
**Purpose:** Automatically identify and rename MKV files produced by MakeMKV, organizing them into a Plex-ready folder structure using media database APIs and LLM-powered intelligence.

### 1.1 Hybrid Architecture

The tool uses a **two-layer design**:
- **PowerShell wrapper** (`rename-media.ps1`) — Thin entry point that validates inputs, ensures the Python virtual environment is set up, and invokes the Python tool. Keeps the UX consistent with the existing `process-dvds.ps1` scripts.
- **Python core** (`media_renamer/`) — All heavy lifting: LLM integration, TMDb API calls, MediaInfo parsing, interactive prompts, and file operations. Python is chosen for its superior LLM SDK support, rich CLI libraries, and existing media-tool ecosystem.

### 1.2 Problem

After ripping DVDs and Blu-rays with MakeMKV, the output files have generic names (e.g., `title_t00.mkv`) and flat folder structures. Before adding to a Plex media server, each file must be:
1. Identified (what movie or TV episode is it?)
2. Renamed to Plex naming conventions
3. Organized into the proper folder hierarchy

This process is currently done entirely by hand and is tedious, especially for multi-disc TV series box sets.

### 1.3 Solution

A Python CLI tool that:
- Scans MakeMKV output directories
- Extracts MKV metadata (duration, audio tracks, chapters)
- Uses an LLM to interpret disc/folder names and correlate files to media
- Queries TMDb for movie/TV episode data including runtimes (and retrieves IMDB/TVDB external IDs)
- Detects and skips "Play All" concatenated tracks
- Matches MKV files to specific movies or TV episodes using duration comparison
- Presents proposed matches to the user for confirmation
- Renames and organizes files (including extras) into a Plex-ready staging directory

---

## 2. User Stories

### US-1: Process a Movie Disc
> As a user, I want to point the tool at a MakeMKV output folder containing a movie rip, have it identify the movie, and rename/organize the main feature into Plex format so I can copy it to my server.

### US-2: Process a TV Series Disc
> As a user, I want to point the tool at a MakeMKV output folder containing a TV series disc, have it identify which episodes are on the disc, match each MKV file to its episode, and rename/organize them so I can copy them to my server.

### US-3: Process Multiple Discs at Once
> As a user, I want to point the tool at a parent directory containing multiple MakeMKV output folders (movies and TV mixed) and have it process all of them in one session.

### US-4: Confirm Matches Before Renaming
> As a user, I want to review and confirm (or correct) the tool's proposed media matches before any files are renamed, so I don't end up with incorrectly labeled media.

### US-5: Handle Ambiguous Content
> As a user, when the tool can't confidently identify content, I want it to present its best guesses and let me choose or manually enter the correct information.

### US-6: Organize Bonus Content
> As a user, I want the tool to identify bonus features and extras and organize them into Plex's extras structure (renaming if possible, or just placing them in the correct location for me to rename later).

### US-7: Handle "Play All" Tracks
> As a user, I want the tool to automatically detect and skip "Play All" concatenated tracks that MakeMKV rips from DVDs (where the disc has a single long track that combines all episodes), so only individual episode files are processed.

---

## 3. Functional Requirements

### 3.1 Input Scanning

| ID | Requirement |
|----|-------------|
| FR-1 | Accept a source directory path containing one or more MakeMKV output folders |
| FR-2 | Accept a destination/staging directory path for Plex-ready output |
| FR-3 | Recursively discover all MKV files within the source directory |
| FR-4 | Group MKV files by their parent folder (each folder = one disc) |
| FR-5 | Extract metadata from each MKV file: duration, audio track count/languages, subtitle count/languages, video resolution, chapter count and names |

### 3.2 Content Identification

| ID | Requirement |
|----|-------------|
| FR-6 | Parse folder names to extract likely media title, season number, and disc number using LLM interpretation |
| FR-7 | Search TMDb API for candidate movie or TV show matches based on parsed title |
| FR-8 | Classify each folder as **Movie**, **TV Series**, or **Unknown** based on file count and duration patterns |
| FR-9 | For movies: match the longest-duration MKV to the movie entry; classify remaining files as extras |
| FR-10 | For TV series: retrieve episode list with runtimes from TMDb for the identified season |
| FR-11 | For TV series: match MKV files to episodes using duration comparison (±3 min tolerance, configurable) |
| FR-12 | Use LLM reasoning to resolve ambiguous matches when algorithmic matching produces multiple candidates |
| FR-13 | Support multi-disc TV series processing with sequential episode mapping across discs |
| FR-14 | Detect "Play All" concatenated tracks — identify MKV files whose duration ≈ the sum of other episode-length files on the disc, and automatically skip them |
| FR-15 | Retrieve external IDs from online databases: IMDB IDs (for movies) and TVDB IDs (for TV shows) to match the user's Plex library conventions |

### 3.3 User Interaction

| ID | Requirement |
|----|-------------|
| FR-16 | Display a summary of each folder being processed: folder name, file count, interpreted media title |
| FR-17 | Present proposed file-to-media mappings in a clear table format before any action is taken |
| FR-18 | Prompt user to **Confirm**, **Edit**, or **Skip** each proposed mapping |
| FR-19 | When editing, allow the user to manually enter the correct movie title, TV show name, season, or episode number |
| FR-20 | When classification is uncertain (Movie vs TV), ask the user to choose |
| FR-21 | Display an overall progress indicator when processing multiple folders |
| FR-22 | At the end of a session, display a summary of all actions taken (files renamed, files skipped, errors) |

### 3.4 File Operations

| ID | Requirement |
|----|-------------|
| FR-23 | Rename MKV files to Plex naming conventions (see §4) |
| FR-24 | Create the proper Plex folder hierarchy in the staging directory |
| FR-25 | **Move** files to the staging directory (relocate from source to destination; originals are not retained in the source location) |
| FR-26 | Include IMDB ID in movie folder/file names (e.g., `{imdb-tt0133093}`) |
| FR-27 | Include TVDB ID in TV show folder names (e.g., `{tvdb-79168}`) |
| FR-28 | Organize extras/bonus features into Plex's extras folder structure (per-season for TV, per-movie for films); rename extras if the LLM can identify them, otherwise place in the correct location for manual renaming |
| FR-29 | Generate a processing log file recording all actions taken |
| FR-30 | Support a **dry-run mode** that shows what would happen without moving/renaming any files |

### 3.5 Configuration

| ID | Requirement |
|----|-------------|
| FR-31 | Store API keys (TMDb, OpenAI) in a `.env` file or environment variables; users register their own keys |
| FR-32 | Use OpenAI as the LLM provider; auto-detect the best available model based on the user's subscription level |
| FR-33 | Allow configuration of duration matching tolerance (default: ±3 minutes) |
| FR-34 | Allow configuration of minimum duration threshold for "real content" vs bonus features (default: 10 minutes) |
| FR-35 | Support a configuration file (e.g., `config.yaml`) for persistent settings |

---

## 4. Plex Naming Convention Specification

> **Note:** These conventions are based on the user's existing Plex library structure, scanned from their media server. All media files retain their original file extension (.mkv, .mp4, etc.).

### 4.1 Movies

**Template:**
```
{StagingDir}/Movies/MovieName (Year) {imdb-ID}/
  MovieName (Year) {imdb-ID}.mkv
```

**Example:**
```
/Staging/Movies/The Matrix (1999) {imdb-tt0133093}/
  The Matrix (1999) {imdb-tt0133093}.mkv
```

### 4.2 TV Shows — Episodes

**Template:**
```
{StagingDir}/TV Shows/ShowName (Year) {tvdb-ID}/
  Season NN/
    ShowName (Year) - sNNeNN - EpisodeTitle.mkv
```

**Example:**
```
/Staging/TV Shows/Friends (1994) {tvdb-79168}/
  Season 01/
    Friends (1994) - s01e01 - The One Where Monica Gets a Roommate.mkv
    Friends (1994) - s01e02 - The One with the Sonogram at the End.mkv
```

### 4.3 Specials / Bonus Content (TV Shows)

TV specials are stored in a `Specials/` folder (not `Season 00/`) and use s00eNN numbering in filenames:

**Template:**
```
{StagingDir}/TV Shows/ShowName (Year) {tvdb-ID}/Specials/
  ShowName (Year) - s00eNN - SpecialTitle.mkv
```

**Example:**
```
/Staging/TV Shows/Band of Brothers (2001) {tvdb-74205}/Specials/
  Band of Brothers (2001) - s00e01 - Premiere in Normandy.mkv
```

### 4.4 Movie Extras (if identified)

**Template:**
```
{StagingDir}/Movies/MovieName (Year) {imdb-ID}/
  MovieName (Year) - behindthescenes-1.mkv
  MovieName (Year) - featurette-1.mkv
```

### 4.5 TV Extras / Featurettes

Unidentified extras are placed in a `Featurettes/` folder for manual review:

**Template:**
```
{StagingDir}/TV Shows/ShowName (Year) {tvdb-ID}/Featurettes/
  OriginalOrBestGuessName.mkv
```

### 4.6 Naming Rules

- All media files **retain their original file extension** (.mkv, .mp4, .avi, etc.)
- **No resolution, bitrate, or codec information** in filenames — only title, year, IDs, and episode info
- Season numbers and episode numbers are always **two digits**, zero-padded (e.g., s01e04)
- IMDB IDs include the `tt` prefix (e.g., imdb-tt0133093)
- TVDB IDs are numeric only (e.g., tvdb-79168)

---

## 5. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | **Platform:** Windows 10/11 (primary), with cross-platform compatibility via Python |
| NFR-2 | **Python version:** 3.12 or higher |
| NFR-3 | **Performance:** Process a typical disc folder (5-10 MKV files) in under 30 seconds (excluding file copy time) |
| NFR-4 | **Error handling:** Gracefully handle API failures, missing metadata, and network issues with clear user messages |
| NFR-5 | **Idempotency:** Running the tool twice on the same input should not create duplicates or corrupt existing output |
| NFR-6 | **No data loss:** Original MKV files are moved (not copied) to the staging directory; the tool never deletes files without user confirmation |
| NFR-7 | **API cost:** Minimize LLM token usage by batching context and using the most cost-effective model available via auto-detection |
| NFR-8 | **Offline fallback:** If LLM API is unavailable, fall back to algorithmic matching only and prompt user for manual input |

---

## 6. Technical Architecture

### 6.1 Component Overview

```
media-renamer/
├── rename-media.ps1         # PowerShell wrapper (entry point)
├── media_renamer/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point (Typer/Click)
│   ├── scanner.py           # Directory scanning & MKV metadata extraction
│   ├── identifier.py        # Content identification (LLM + TMDb)
│   ├── matcher.py           # Duration-based episode matching algorithm
│   ├── renamer.py           # File renaming & folder structure creation
│   ├── prompts.py           # LLM prompt templates
│   ├── ui.py                # Interactive user prompts & display
│   ├── config.py            # Configuration management
│   └── models.py            # Pydantic data models
├── tests/
├── .env.example
├── config.yaml.example
├── pyproject.toml
└── README.md
```

### 6.2 Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `typer` | ≥0.9 | CLI framework with auto-generated help |
| `rich` | ≥13.0 | Beautiful terminal output, tables, progress |
| `questionary` | ≥2.0 | Interactive prompts and selections |
| `tmdbv3api` | ≥1.9 | TMDb API client (also provides IMDB/TVDB external IDs) |
| `pymediainfo` | ≥6.0 | MKV metadata extraction |
| `openai` | ≥1.0 | LLM API calls (auto-detects best available model) |
| `pydantic` | ≥2.0 | Data validation and models |
| `python-dotenv` | ≥1.0 | Environment variable management |
| `pyyaml` | ≥6.0 | Configuration file parsing |

### 6.3 Data Flow

```
1. User runs:  media-renamer --source /rips --dest /staging

2. SCAN PHASE
   └─> Walk source directory
   └─> Group MKVs by parent folder
   └─> Extract metadata via MediaInfo (duration, audio, subs)
   └─> Detect and flag "Play All" concatenated tracks for skipping

3. IDENTIFY PHASE (per folder)
   └─> Send folder name + file summary to LLM
   └─> LLM returns: likely title, content type, season/disc info
   └─> Search TMDb for the identified title
   └─> Retrieve external IDs (IMDB for movies, TVDB for TV)
   └─> Present top matches to user → user confirms or corrects

4. MATCH PHASE (per folder)
   └─> For movies: longest file = main feature; classify extras
   └─> For TV: compare file durations to TMDb episode runtimes
   └─> LLM resolves ambiguous matches
   └─> Present proposed mapping to user → user confirms or edits

5. RENAME PHASE
   └─> Build Plex-compliant folder structure in staging dir
   └─> Move files with new names (including extras)
   └─> Log all actions

6. SUMMARY
   └─> Display what was processed, any skips or errors
```

---

## 7. User Experience Flow

### 7.1 Example Session

```
$ media-renamer --source E:\MakeMKV_Output --dest E:\PlexStaging

╭─────────────────────────────────────────────────╮
│           Media Renamer v1.0                    │
│     Scanning: E:\MakeMKV_Output                 │
╰─────────────────────────────────────────────────╯

Found 3 folders to process:

  1. THE_MATRIX        → 4 MKV files
  2. FRIENDS_S2_D3     → 6 MKV files
  3. INCEPTION_DISC1   → 2 MKV files

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Processing: THE_MATRIX

  🤖 AI Analysis: "The Matrix" (1999) — Movie
  📊 IMDB: tt0133093 | TMDb: 603

  ┌───────┬────────────────────┬──────────┬────────────────┐
  │ File  │ Source             │ Duration │ Proposed Match │
  ├───────┼────────────────────┼──────────┼────────────────┤
  │ t00   │ THE_MATRIX_t00.mkv │ 2:16:15  │ ✅ Main Feature │
  │ t01   │ THE_MATRIX_t01.mkv │ 0:05:23  │ 📦 Extra       │
  │ t02   │ THE_MATRIX_t02.mkv │ 0:03:11  │ 📦 Extra       │
  │ t03   │ THE_MATRIX_t03.mkv │ 0:02:45  │ 📦 Extra       │
  └───────┴────────────────────┴──────────┴────────────────┘

  Output: Movies/The Matrix (1999) {imdb-tt0133093}/The Matrix (1999) {imdb-tt0133093}.mkv

  ? Accept this mapping? [Confirm / Edit / Skip]  › Confirm
  ✅ Moved and renamed successfully.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Processing: FRIENDS_S2_D3

  🤖 AI Analysis: "Friends" Season 2, Disc 3 — TV Series
  📊 TVDB: 79168 | TMDb: 1668

  ┌───────┬──────────────────────────┬──────────┬──────────────────────────────────┐
  │ File  │ Source                   │ Duration │ Proposed Match                   │
  ├───────┼──────────────────────────┼──────────┼──────────────────────────────────┤
  │ t00   │ FRIENDS_S2_D3_t00.mkv   │ 2:45:12  │ ⏭️  Play All (skip)              │
  │ t01   │ FRIENDS_S2_D3_t01.mkv   │ 0:22:18  │ s02e09 - The One with Phoebe's…  │
  │ t02   │ FRIENDS_S2_D3_t02.mkv   │ 0:22:05  │ s02e10 - The One with Russ       │
  │ t03   │ FRIENDS_S2_D3_t03.mkv   │ 0:22:31  │ s02e11 - The One with the Lesb…  │
  │ t04   │ FRIENDS_S2_D3_t04.mkv   │ 0:22:12  │ s02e12 - The One After the Sup…  │
  │ t05   │ FRIENDS_S2_D3_t05.mkv   │ 0:01:30  │ 📦 Extra                         │
  └───────┴──────────────────────────┴──────────┴──────────────────────────────────┘

  ? Accept this mapping? [Confirm / Edit / Skip]  › Confirm
  ✅ Moved and renamed 4 episodes, 1 extra. Skipped 1 Play All track.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
...

Session Complete!
  ✅ 2 movies processed
  ✅ 4 TV episodes processed
  📦 4 extras organized
  ⏭️  1 Play All track skipped
  📝 Log saved to: E:\PlexStaging\media_renamer.log
```

---

## 8. MVP Scope (v1.0)

The initial release should include:

- [x] Directory scanning and MKV metadata extraction
- [x] "Play All" concatenated track detection and skipping
- [x] LLM-powered folder name interpretation (OpenAI, auto-detect best model)
- [x] TMDb search and episode/movie lookup with IMDB/TVDB external ID retrieval
- [x] Duration-based episode matching
- [x] Interactive user confirmation for all matches
- [x] Plex-compliant file renaming and folder creation (IMDB IDs for movies, TVDB IDs for TV)
- [x] Move to staging directory (non-destructive in dry-run mode)
- [x] Extras/bonus feature organization into Plex extras structure
- [x] Dry-run mode
- [x] Processing log

### Deferred to v2.0

- [ ] Chapter name analysis for additional matching signals
- [ ] Subtitle/audio track language-based hints
- [ ] TheTVDB direct API integration as fallback
- [ ] Batch/unattended mode with saved preferences
- [ ] Integration with Plex API to verify library additions
- [ ] Web UI alternative to CLI

---

## 9. Success Criteria

1. Tool correctly identifies and renames ≥90% of media from typical MakeMKV output without manual corrections
2. User interaction is required only for confirmation, not data entry, in the common case
3. Processing time is under 30 seconds per disc folder (excluding file move time)
4. Files are moved cleanly — no partial moves or corrupted files on interruption
5. Output folder structure passes Plex's media scanner without naming warnings

---

## 10. Resolved Questions

| # | Question | Resolution |
|---|----------|------------|
| 1 | **Plex folder conventions** | Scanned user's existing Plex library. Movies use `{imdb-ttXXXX}` IDs, TV shows use `{tvdb-XXXXX}` IDs. Specials folder is named `Specials/` not `Season 00/`. No resolution/bitrate in filenames. Movie filenames include the IMDB tag; episode filenames do not include the TVDB tag. See §4 for full spec. |
| 2 | **API key management** | Users register their own API keys (TMDb, OpenAI) and store them in a `.env` file. Takes ~2 minutes per service. |
| 3 | **Sample data** | Validated against Gilmore Girls S1-S2 (12 discs, 60+ MKV files). Confirmed "Play All" track detection, duration matching, and bonus content identification algorithms work. See Research document §12 for details. |
| 4 | **LLM provider** | OpenAI with auto-detection of the best available model based on the user's subscription level. |
| 5 | **Extras handling** | Extras are organized into Plex's extras folder structure — per-movie for films, per-season or `Featurettes/` folder for TV. Renamed by LLM if identifiable, otherwise placed for manual review. |
| 6 | **Copy vs Move** | Files are **moved** (not copied) from source to staging directory. Dry-run mode previews without moving. |

---

## 11. Implementation Plan — Phased Delivery

This plan breaks the MVP into phases that can be implemented and tested incrementally across multiple Copilot sessions. Each phase produces working, testable functionality.

### Phase 1: Project Scaffolding & Core Infrastructure
**Goal:** Set up the project structure, dependencies, configuration, and data models.

- Initialize Python project with `pyproject.toml` and virtual environment
- Create `rename-media.ps1` PowerShell wrapper (venv setup, argument passing)
- Implement configuration management (`config.py`) — `.env` loading, `config.yaml` parsing
- Define Pydantic data models (`models.py`) — `MediaFile`, `DiscFolder`, `MovieMatch`, `EpisodeMatch`, `ProcessingResult`
- Create `.env.example` and `config.yaml.example` with documented settings
- Set up basic CLI entry point (`cli.py`) with `--source`, `--dest`, and `--dry-run` arguments
- Write unit tests for configuration and models

### Phase 2: MKV Scanning & Metadata Extraction
**Goal:** Scan directories, extract metadata, detect "Play All" tracks and bonus content.

- Implement directory scanner (`scanner.py`) — recursive MKV discovery, group by parent folder
- Implement MediaInfo-based metadata extraction (duration, audio tracks, subtitle tracks, chapter info)
- Implement "Play All" track detection algorithm (duration ≈ sum of episode-length files)
- Implement bonus content classification (configurable duration threshold, default 10 min)
- Implement file ordering heuristics (sort by track position letter for episode order)
- Write unit tests with mock metadata matching the Gilmore Girls sample dataset
- Manual validation: run scanner against `D:\Video\processed` and verify output

### Phase 3: TMDb Integration & Content Identification
**Goal:** Search TMDb, retrieve movie/TV data, and get IMDB/TVDB external IDs.

- Implement TMDb API client wrapper (`identifier.py`) — search movies, search TV shows
- Implement season/episode data retrieval with per-episode runtimes
- Implement external ID retrieval (IMDB IDs for movies, TVDB IDs for TV shows)
- Implement content type classification logic (Movie vs TV vs Unknown based on file patterns)
- Write unit tests with mocked TMDb responses
- Integration test: verify TMDb lookups for Gilmore Girls, Band of Brothers, The Matrix

### Phase 4: LLM Integration & Folder Name Interpretation
**Goal:** Use OpenAI to parse folder names and resolve ambiguous matches.

- Implement OpenAI client with auto-detection of best available model (`prompts.py`)
- Design and implement LLM prompt templates for:
  - Folder name interpretation (extract title, season, disc number)
  - Ambiguous match resolution (when duration matching gives multiple candidates)
  - Extras identification (classify bonus content type for Plex naming)
- Implement fallback behavior when LLM API is unavailable (algorithmic matching + user input)
- Write unit tests with mocked LLM responses
- Manual test: run folder name interpretation against all 12 Gilmore Girls folder names

### Phase 5: Duration-Based Episode Matching
**Goal:** Match MKV files to specific episodes using duration comparison.

- Implement duration matching algorithm (`matcher.py`) — compare file durations to TMDb runtimes
- Implement configurable tolerance (default ±3 min)
- Implement sequential disc mapping (track episode count across discs for multi-disc sets)
- Implement LLM arbitration for ambiguous matches
- Implement match confidence scoring (High/Medium/Low)
- Write unit tests using Gilmore Girls sample data + TMDb runtimes
- Manual validation: verify correct episode assignment for all 12 sample discs

### Phase 6: Interactive User Interface
**Goal:** Build the interactive confirmation UI with rich terminal output.

- Implement rich terminal display (`ui.py`) — folder summaries, file tables, progress indicators
- Implement interactive prompts — Confirm/Edit/Skip for each folder mapping
- Implement manual override workflows (edit title, season, episode number)
- Implement session summary display (processed, skipped, errors)
- Implement dry-run output formatting
- Manual test: full interactive session with sample data

### Phase 7: File Operations & Plex Structure
**Goal:** Move and rename files into the Plex-compliant folder structure.

- Implement Plex folder structure builder (`renamer.py`) — create directory hierarchy
- Implement file renaming with correct naming conventions (IMDB IDs, TVDB IDs, episode titles)
- Implement extras organization (movie extras, TV featurettes, specials)
- Implement move operations with error handling (partial move recovery)
- Implement processing log generation
- Write unit tests for filename generation and path construction
- Integration test: dry-run against sample data, verify all proposed paths are correct

### Phase 8: End-to-End Testing & Polish
**Goal:** Full pipeline testing, edge case handling, and documentation.

- End-to-end testing with Gilmore Girls sample dataset
- Test with movie content (if available)
- Handle edge cases: empty folders, no TMDb match, API failures, network timeouts
- Error handling and graceful degradation throughout the pipeline
- Update README.md with final usage instructions and examples
- Final manual validation: process sample discs and verify Plex accepts the output
