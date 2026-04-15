# DVD Ripping Tools

A collection of tools for ripping DVDs/Blu-rays and organizing the resulting media files for a Plex media server.

## Tools

### 1. MakeMKV Processing Scripts (PowerShell)

Batch-process DVDs and Blu-rays using [MakeMKV](https://www.makemkv.com/) to extract MKV files from ISO images and BDMV disc structures.

#### `process-dvds.ps1`
Processes all `.iso` files and `index.bdmv` files in a directory, writing MakeMKV output to log files (quiet mode).

```powershell
.\process-dvds.ps1 -inputDirectory "D:\Rips" -outputDirectory "D:\Video\processed"
```

#### `processToScreen-dvds.ps1`
Same as above but displays MakeMKV output directly to the console and provides a summary of successes and failures at the end.

```powershell
.\processToScreen-dvds.ps1 -inputDirectory "D:\Rips" -outputDirectory "D:\Video\processed"
```

**Requirements:**
- Windows 10/11
- [MakeMKV](https://www.makemkv.com/) installed (default path: `C:\Program Files (x86)\MakeMKV\makemkvcon64.exe`)

### 2. Media Renamer

An intelligent CLI tool that automatically identifies and renames MKV files produced by MakeMKV, organizing them into a Plex-ready folder structure.

**Key features:**
- Scans MakeMKV output directories and extracts metadata (duration, audio, subtitles)
- Uses OpenAI LLM to interpret cryptic disc labels (e.g., `FRIENDS_S2_D3` → "Friends, Season 2, Disc 3")
- Queries TMDb for movie/TV episode data and retrieves IMDB/TVDB IDs
- Detects and skips "Play All" concatenated tracks automatically
- Matches MKV files to specific episodes using duration comparison
- Interactive confirmation before any files are moved
- Organizes extras/bonus features into Plex's extras structure
- Dry-run mode to preview changes without moving files

**Tech stack:** Python 3.12+ core with PowerShell wrapper

See [Media_Renamer_PRD.md](Media_Renamer_PRD.md) for the full product requirements document and [Media_Renamer_Research.md](Media_Renamer_Research.md) for research notes.

#### Prerequisites

1. **Python 3.12 or higher** must be installed and available on your `PATH`.
   - Download from [python.org](https://www.python.org/downloads/) — during installation, check **"Add Python to PATH"**.
   - Verify it's installed by opening PowerShell and running:
     ```powershell
     python --version
     ```
     You should see `Python 3.12.x` (or higher).

2. **API keys** — the tool uses two external services that require free API keys:
   - **TMDb** (The Movie Database) — for looking up movies/TV shows and episode data.
     Register for a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api).
   - **OpenAI** — for the LLM-powered disc name interpretation.
     Get a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

#### Setup (First-Time)

The **easiest way** is to just run `rename-media.ps1` — it automatically creates a Python virtual environment and installs all dependencies the first time it runs. No manual steps required beyond having Python installed.

If you prefer to set things up manually (or want to run tests), open PowerShell in the project directory and run:

```powershell
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate it
.\.venv\Scripts\Activate.ps1

# 3. Install the project and its dependencies (including test tools)
pip install -e ".[dev]"
```

> **What does this do?**
> - `python -m venv .venv` creates an isolated Python environment in a `.venv/` folder so packages don't interfere with other Python projects on your machine.
> - `Activate.ps1` tells your current PowerShell session to use that environment.
> - `pip install -e ".[dev]"` installs Media Renamer and all its dependencies into the virtual environment. The `-e` flag means "editable" — changes you make to the source code take effect immediately without reinstalling.

#### Configuring API Keys

Copy the example environment file and fill in your keys:

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace the placeholder values with your actual API keys:
```
TMDB_API_KEY=your_actual_tmdb_key
OPENAI_API_KEY=your_actual_openai_key
```

You can also customize matching settings by copying the config file:
```powershell
Copy-Item config.yaml.example config.yaml
```

#### Usage

```powershell
# Via the PowerShell wrapper (recommended — handles venv automatically):
.\rename-media.ps1 -Source "E:\MakeMKV_Output" -Dest "E:\PlexStaging"

# Dry-run mode (preview only, no files moved):
.\rename-media.ps1 -Source "E:\MakeMKV_Output" -Dest "E:\PlexStaging" -DryRun

# Or directly via Python (if you activated the venv manually):
media-renamer --source "E:\MakeMKV_Output" --dest "E:\PlexStaging" --dry-run
```

#### Running Tests

```powershell
# Activate the venv first (if not already active)
.\.venv\Scripts\Activate.ps1

# Run all tests
pytest tests/ -v
```

## Typical Workflow

```
1. Rip DVDs/Blu-rays     →  process-dvds.ps1 (MakeMKV automation)
2. Identify & rename      →  rename-media.ps1 (Media Renamer)
3. Move to Plex library   →  (handled automatically by step 2)
```

### Media Renamer Example

```powershell
# Dry-run (preview only — no files moved)
.\rename-media.ps1 --source D:\Video\processed --dest \\server\videos --dry-run

# Live run
.\rename-media.ps1 --source D:\Video\processed --dest \\server\videos

# Disable auto-grouping (process each disc individually)
.\rename-media.ps1 --source D:\Video\processed --dest \\server\videos --no-batch
```

#### Batch Mode (default)

When multiple discs of the same TV show/season are detected, the tool
auto-groups them and processes the entire batch with a single confirmation.
Each disc's episodes cascade from where the previous disc left off:

```
📦 Batch Grouping Results

  #  Show            Season  Discs  Folders
  1  Gilmore Girls   S01     6      GG_S1_D1, GG_S1_D2, ..., GG_S1_D6
  2  Gilmore Girls   S02     6      GG_S2_D1, GG_S2_D2, ..., GG_S2_D6

  + 1 ungrouped folder(s) (will process individually)

  Gilmore Girls (2000) — Season 1
  21 episode(s) across 6 disc(s)

? Process all 6 discs of Gilmore Girls Season 1? ✅ Confirm

  ✅ GG_S1_D1 — 4 episode(s) — 1 skipped — 1 extra(s)
  ✅ GG_S1_D2 — 4 episode(s) — 1 skipped
  ✅ GG_S1_D3 — 4 episode(s) — 1 skipped
  ✅ GG_S1_D4 — 4 episode(s) — 1 skipped
  ✅ GG_S1_D5 — 4 episode(s) — 1 skipped
  ✅ GG_S1_D6 — 1 episode(s) — 1 skipped
```

#### Single Disc / Movie (interactive)

Standalone discs and movies use the interactive per-folder flow with
confirmation before each move:

```
┌─ GILMORE_GIRLS_S1_US_D1 ──────────────────────────────────────────────┐
│  Identified: Gilmore Girls (2000) — Season 1                          │
│  TMDb: 4586 · TVDB: 76568                                            │
│                                                                       │
│  Episodes:                                                            │
│    s01e01 — Pilot                            44.2 min  ✓ HIGH         │
│    s01e02 — The Lorelais' First Day …        43.2 min  ✓ HIGH         │
│    s01e03 — Kill Me Now                      44.0 min  ✓ HIGH         │
│    s01e04 — The Deer Hunters                 44.5 min  ✓ HIGH         │
│  Skipped: 1 Play-All · 1 Bonus                                       │
└───────────────────────────────────────────────────────────────────────┘
  [Confirm]  [Edit]  [Skip]
```

Output structure:
```
TV Shows/Gilmore Girls (2000) {tvdb-76568}/
  Season 01/
    Gilmore Girls (2000) - s01e01 - Pilot.mkv
    Gilmore Girls (2000) - s01e02 - The Lorelais' First Day at Chilton.mkv
    ...
Movies/The Matrix (1999) {imdb-tt0133093}/
  The Matrix (1999) {imdb-tt0133093}.mkv
```

## Plex Naming Conventions

This toolset targets the following Plex-compatible naming structure:

**Movies:**
```
Movies/Movie Name (Year) {imdb-ttXXXXXXX}/
  Movie Name (Year) {imdb-ttXXXXXXX}.mkv
```

**TV Shows:**
```
TV Shows/Show Name (Year) {tvdb-XXXXX}/
  Season 01/
    Show Name (Year) - s01e01 - Episode Title.mkv
```

## License

This project is for personal use.
