# Media Renamer — Product Requirements Document (PRD)

## 1. Overview

**Product Name:** Media Renamer
**Type:** Command-line tool (Python core with PowerShell wrapper)
**Purpose:** Automatically identify and rename MKV files produced by MakeMKV, organizing them into a Plex-ready folder structure using media database APIs and LLM-powered intelligence.

### 1.0.1 Hybrid Architecture

The tool uses a **two-layer design**:
- **PowerShell wrapper** (`rename-media.ps1`) — Thin entry point that validates inputs, ensures the Python virtual environment is set up, and invokes the Python tool. Keeps the UX consistent with the existing `process-dvds.ps1` scripts.
- **Python core** (`media_renamer/`) — All heavy lifting: LLM integration, TMDb API calls, MediaInfo parsing, interactive prompts, and file operations. Python is chosen for its superior LLM SDK support, rich CLI libraries, and existing media-tool ecosystem.

### 1.1 Problem

After ripping DVDs and Blu-rays with MakeMKV, the output files have generic names (e.g., `title_t00.mkv`) and flat folder structures. Before adding to a Plex media server, each file must be:
1. Identified (what movie or TV episode is it?)
2. Renamed to Plex naming conventions
3. Organized into the proper folder hierarchy

This process is currently done entirely by hand and is tedious, especially for multi-disc TV series box sets.

### 1.2 Solution

A Python CLI tool that:
- Scans MakeMKV output directories
- Extracts MKV metadata (duration, audio tracks, chapters)
- Uses an LLM to interpret disc/folder names and correlate files to media
- Queries TMDb for movie/TV episode data including runtimes
- Matches MKV files to specific movies or TV episodes
- Presents proposed matches to the user for confirmation
- Renames and organizes files into a Plex-ready staging directory

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

### US-6: Skip Bonus Content
> As a user, I want the tool to identify and optionally skip short bonus features, trailers, and extras, focusing on the main content.

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
| FR-9 | For movies: match the longest-duration MKV to the movie entry; flag remaining files as potential extras |
| FR-10 | For TV series: retrieve episode list with runtimes from TMDb for the identified season |
| FR-11 | For TV series: match MKV files to episodes using duration comparison (±3 min tolerance) |
| FR-12 | Use LLM reasoning to resolve ambiguous matches when algorithmic matching produces multiple candidates |
| FR-13 | Support multi-disc TV series processing with sequential episode mapping across discs |

### 3.3 User Interaction

| ID | Requirement |
|----|-------------|
| FR-14 | Display a summary of each folder being processed: folder name, file count, interpreted media title |
| FR-15 | Present proposed file-to-media mappings in a clear table format before any action is taken |
| FR-16 | Prompt user to **Confirm**, **Edit**, or **Skip** each proposed mapping |
| FR-17 | When editing, allow the user to manually enter the correct movie title, TV show name, season, or episode number |
| FR-18 | When classification is uncertain (Movie vs TV), ask the user to choose |
| FR-19 | Display an overall progress indicator when processing multiple folders |
| FR-20 | At the end of a session, display a summary of all actions taken (files renamed, files skipped, errors) |

### 3.4 File Operations

| ID | Requirement |
|----|-------------|
| FR-21 | Rename MKV files to Plex naming conventions (see §4) |
| FR-22 | Create the proper Plex folder hierarchy in the staging directory |
| FR-23 | **Copy** files to the staging directory (do not move/delete originals) |
| FR-24 | Include TMDb ID in folder names for improved Plex matching (e.g., `{tmdb-603}`) |
| FR-25 | Generate a processing log file recording all actions taken |
| FR-26 | Support a **dry-run mode** that shows what would happen without copying/renaming any files |

### 3.5 Configuration

| ID | Requirement |
|----|-------------|
| FR-27 | Store API keys (TMDb, LLM provider) in a `.env` file or environment variables |
| FR-28 | Allow configuration of the LLM provider (OpenAI, Anthropic, or local via Ollama) |
| FR-29 | Allow configuration of duration matching tolerance (default: ±3 minutes) |
| FR-30 | Allow configuration of minimum duration threshold for "real content" vs bonus features (default: 10 minutes) |
| FR-31 | Support a configuration file (e.g., `config.yaml`) for persistent settings |
| FR-32 | Allow the user to define custom Plex naming templates if their conventions differ from defaults |

---

## 4. Plex Naming Convention Specification

### 4.1 Movies

```
{StagingDir}/Movies/{MovieName} ({Year}) {tmdb-{ID}}/
  {MovieName} ({Year}).mkv
```

**Example:**
```
/Staging/Movies/The Matrix (1999) {tmdb-603}/
  The Matrix (1999).mkv
```

### 4.2 TV Shows — Episodes

```
{StagingDir}/TV Shows/{ShowName} ({Year}) {tmdb-{ID}}/
  Season {NN}/
    {ShowName} ({Year}) - s{NN}e{NN} - {EpisodeTitle}.mkv
```

**Example:**
```
/Staging/TV Shows/Band of Brothers (2001) {tmdb-4613}/
  Season 01/
    Band of Brothers (2001) - s01e04 - Replacements.mkv
    Band of Brothers (2001) - s01e05 - Crossroads.mkv
    Band of Brothers (2001) - s01e06 - Bastogne.mkv
```

### 4.3 Specials / Bonus Content (if user chooses to keep)

```
{StagingDir}/TV Shows/{ShowName} ({Year})/Season 00/
  {ShowName} ({Year}) - s00e{NN} - {SpecialTitle}.mkv
```

### 4.4 Movie Extras (if user chooses to keep)

```
{StagingDir}/Movies/{MovieName} ({Year}) {tmdb-{ID}}/
  {MovieName} ({Year}) - behindthescenes-1.mkv
  {MovieName} ({Year}) - featurette-1.mkv
```

---

## 5. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | **Platform:** Windows 10/11 (primary), with cross-platform compatibility via Python |
| NFR-2 | **Python version:** 3.12 or higher |
| NFR-3 | **Performance:** Process a typical disc folder (5-10 MKV files) in under 30 seconds (excluding file copy time) |
| NFR-4 | **Error handling:** Gracefully handle API failures, missing metadata, and network issues with clear user messages |
| NFR-5 | **Idempotency:** Running the tool twice on the same input should not create duplicates or corrupt existing output |
| NFR-6 | **No data loss:** Original MKV files are never modified or deleted; the tool only copies to the staging directory |
| NFR-7 | **API cost:** Minimize LLM token usage by batching context and using the most cost-effective model (GPT-4o-mini default) |
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
| `tmdbv3api` | ≥1.9 | TMDb API client |
| `pymediainfo` | ≥6.0 | MKV metadata extraction |
| `openai` | ≥1.0 | LLM API calls (OpenAI) |
| `anthropic` | ≥0.20 | LLM API calls (Anthropic, optional) |
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

3. IDENTIFY PHASE (per folder)
   └─> Send folder name + file summary to LLM
   └─> LLM returns: likely title, content type, season/disc info
   └─> Search TMDb for the identified title
   └─> Present top matches to user → user confirms or corrects

4. MATCH PHASE (per folder)
   └─> For movies: longest file = main feature
   └─> For TV: compare file durations to TMDb episode runtimes
   └─> LLM resolves ambiguous matches
   └─> Present proposed mapping to user → user confirms or edits

5. RENAME PHASE
   └─> Build Plex-compliant folder structure in staging dir
   └─> Copy files with new names
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
  📊 TMDb Match: The Matrix (1999) [tmdb-603] — 136 min

  ┌───────┬────────────────────┬──────────┬────────────────┐
  │ File  │ Source             │ Duration │ Proposed Match │
  ├───────┼────────────────────┼──────────┼────────────────┤
  │ t00   │ THE_MATRIX_t00.mkv │ 2:16:15  │ ✅ Main Feature │
  │ t01   │ THE_MATRIX_t01.mkv │ 0:05:23  │ ⏭️  Bonus (skip)│
  │ t02   │ THE_MATRIX_t02.mkv │ 0:03:11  │ ⏭️  Bonus (skip)│
  │ t03   │ THE_MATRIX_t03.mkv │ 0:02:45  │ ⏭️  Bonus (skip)│
  └───────┴────────────────────┴──────────┴────────────────┘

  Output: Movies/The Matrix (1999) {tmdb-603}/The Matrix (1999).mkv

  ? Accept this mapping? [Confirm / Edit / Skip]  › Confirm
  ✅ Copied and renamed successfully.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Processing: FRIENDS_S2_D3

  🤖 AI Analysis: "Friends" Season 2, Disc 3 — TV Series
  📊 TMDb Match: Friends (1994) [tmdb-1668] — Season 2

  ┌───────┬──────────────────────────┬──────────┬──────────────────────────────────┐
  │ File  │ Source                   │ Duration │ Proposed Match                   │
  ├───────┼──────────────────────────┼──────────┼──────────────────────────────────┤
  │ t00   │ FRIENDS_S2_D3_t00.mkv   │ 0:22:18  │ s02e09 - The One with Phoebe's Dad│
  │ t01   │ FRIENDS_S2_D3_t01.mkv   │ 0:22:05  │ s02e10 - The One with Russ       │
  │ t02   │ FRIENDS_S2_D3_t02.mkv   │ 0:22:31  │ s02e11 - The One with the Lesbian…│
  │ t03   │ FRIENDS_S2_D3_t03.mkv   │ 0:22:12  │ s02e12 - The One After the Super…│
  │ t04   │ FRIENDS_S2_D3_t04.mkv   │ 0:01:30  │ ⏭️  Bonus (skip)                 │
  │ t05   │ FRIENDS_S2_D3_t05.mkv   │ 0:01:15  │ ⏭️  Bonus (skip)                 │
  └───────┴──────────────────────────┴──────────┴──────────────────────────────────┘

  ? Accept this mapping? [Confirm / Edit / Skip]  › Confirm
  ✅ Copied and renamed 4 episodes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
...

Session Complete!
  ✅ 2 movies processed
  ✅ 4 TV episodes processed
  ⏭️  6 bonus features skipped
  📝 Log saved to: E:\PlexStaging\media_renamer.log
```

---

## 8. MVP Scope (v1.0)

The initial release should include:

- [x] Directory scanning and MKV metadata extraction
- [x] LLM-powered folder name interpretation
- [x] TMDb search and episode/movie lookup
- [x] Duration-based episode matching
- [x] Interactive user confirmation for all matches
- [x] Plex-compliant file renaming and folder creation
- [x] Copy to staging directory (non-destructive)
- [x] Dry-run mode
- [x] Processing log

### Deferred to v2.0

- [ ] Chapter name analysis for additional matching signals
- [ ] Subtitle/audio track language-based hints
- [ ] TheTVDB fallback integration
- [ ] Batch/unattended mode with saved preferences
- [ ] Custom user naming templates
- [ ] Integration with Plex API to verify library additions
- [ ] Web UI alternative to CLI

---

## 9. Success Criteria

1. Tool correctly identifies and renames ≥90% of media from typical MakeMKV output without manual corrections
2. User interaction is required only for confirmation, not data entry, in the common case
3. Processing time is under 30 seconds per disc folder (excluding file copy)
4. No original files are ever modified or deleted
5. Output folder structure passes Plex's media scanner without naming warnings

---

## 10. Open Questions

1. **User's Plex folder conventions** — Need to confirm the user's existing folder structure and naming patterns on their Plex server to ensure compatibility
2. **API key management** — Should we use a shared TMDb API key or require the user to register their own?
3. **Sample data** — User mentioned they can point us at a sample set of MakeMKV output; this will be critical for testing
4. **LLM provider preference** — OpenAI, Anthropic, or local (Ollama)?
5. **Extras handling** — Should bonus features be completely ignored, or organized into Plex's extras structure?
