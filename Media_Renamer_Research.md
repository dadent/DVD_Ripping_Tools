# Media Renamer Tool — Research Notes

## 1. Problem Statement

After ripping DVDs and Blu-rays with MakeMKV (via the `process-dvds.ps1` scripts), the resulting MKV files are dumped into folders with generic names (e.g., `The Matrix_t00.mkv`, `Disc1_t01.mkv`). Before copying to a Plex server, each file must be manually identified—movie or TV episode—and renamed to Plex naming conventions. This is time-consuming and error-prone. We want to automate this process using media database APIs and LLM-based intelligence.

---

## 2. MakeMKV Output — What We're Working With

MakeMKV's default output structure looks like this:

```
/OutputDir/
  /The Matrix/
    The Matrix_t00.mkv    (main feature)
    The Matrix_t01.mkv    (bonus feature / alternate cut)
  /FRIENDS_DISC1/
    FRIENDS_DISC1_t00.mkv
    FRIENDS_DISC1_t01.mkv
    FRIENDS_DISC1_t02.mkv
    FRIENDS_DISC1_t03.mkv
```

**Key observations:**
- Folder name comes from disc metadata (often the disc label/volume name)
- File names use the pattern `{FolderName}_t{NN}.mkv`
- Movies typically have 1 long main feature + several short bonus clips
- TV series discs have multiple similarly-lengthed tracks (one per episode)
- Disc labels are often cryptic (e.g., `FRIENDS_S2_D3`, `BAND_OF_BROTHERS`)
- No embedded episode/movie metadata—just raw video tracks

**Useful metadata we can extract from each MKV:**
- Duration (critical for matching episodes by runtime)
- Number of audio/subtitle tracks and languages
- Video resolution and codec
- Chapter count and chapter names (sometimes contain episode titles)

---

## 3. Media Database APIs — Comparison & Recommendations

### 3.1 TMDb (The Movie Database) — ⭐ PRIMARY RECOMMENDATION

| Aspect | Details |
|--------|---------|
| **Coverage** | Movies + TV shows, seasons, episodes |
| **Free tier** | Generous; free API key for non-commercial use |
| **Episode runtimes** | Yes — per-episode runtime in minutes |
| **Search** | `/search/movie`, `/search/tv` endpoints |
| **Season detail** | `/tv/{id}/season/{num}` returns all episodes with runtimes |
| **Python library** | `tmdbv3api` on PyPI |
| **Attribution** | Required ("Powered by TMDb") |

**Why TMDb is best for this tool:**
- Single API covers both movies AND TV shows
- Episode-level runtime data enables duration-based matching
- Free, well-documented, excellent Python support
- Returns IMDb IDs for cross-referencing

### 3.2 OMDb (Open Movie Database) — SUPPLEMENTARY

| Aspect | Details |
|--------|---------|
| **Coverage** | Movies + basic TV info |
| **Free tier** | 1,000 requests/day free |
| **Strengths** | Returns IMDb ratings, Rotten Tomatoes scores |
| **Weakness** | Limited TV episode detail; no per-episode runtimes |
| **Use case** | Cross-reference IMDb IDs, fetch ratings for display |

### 3.3 TheTVDB — SUPPLEMENTARY FOR TV

| Aspect | Details |
|--------|---------|
| **Coverage** | TV-focused; excellent episode guides |
| **Free tier** | Free for non-commercial with API key |
| **Strengths** | Detailed episode data, air dates, episode images |
| **Weakness** | Limited movie data; Plex uses TMDb now as primary |
| **Use case** | Fallback for TV episode data if TMDb is incomplete |

### 3.4 Blu-ray.com — LIMITED USEFULNESS

- **No public API** available
- Web scraping is possible but fragile (site structure changes)
- **Disq APIs** offer some Blu-ray/DVD metadata via GraphQL
- **BDInfo** tool can inspect physical disc structures
- **Recommendation:** Not worth the complexity; TMDb episode runtimes + LLM matching are more reliable

### 3.5 Recommended API Strategy

```
Primary:   TMDb API (movies + TV + episode runtimes)
Secondary: OMDb API (IMDb ID cross-reference, ratings)
Fallback:  TheTVDB (edge cases for TV episode data)
```

---

## 4. MKV Metadata Extraction Tools

### 4.1 MediaInfo — ⭐ RECOMMENDED

```powershell
# Get duration in milliseconds
mediainfo --Inform="General;%Duration%" movie.mkv

# Get duration in human-readable format
mediainfo --Inform="General;%Duration/String3%" movie.mkv

# Get title if embedded
mediainfo --Inform="General;%Title%" movie.mkv

# JSON output for scripting
mediainfo --Output=JSON movie.mkv
```

- Cross-platform, lightweight CLI
- Very scriptable with custom output templates
- Available via `winget install MediaArea.MediaInfo.CLI` on Windows

### 4.2 ffprobe (FFmpeg) — ALTERNATIVE

```bash
# Duration as JSON
ffprobe -v quiet -of json -show_entries format=duration movie.mkv

# Chapters (may contain episode info)
ffprobe -v quiet -print_format json -show_chapters movie.mkv
```

- More verbose but outputs clean JSON
- Already installed if FFmpeg is present
- Good for chapter extraction

### 4.3 Recommendation

Use **MediaInfo CLI** as primary (simple, fast, scriptable). Use **ffprobe** for chapter extraction when needed.

---

## 5. Technology Platform — Python vs PowerShell

### 5.1 Comparison

| Factor | Python | PowerShell |
|--------|--------|------------|
| **API integration** | Excellent (`requests`, `tmdbv3api`) | Possible but verbose (`Invoke-RestMethod`) |
| **LLM integration** | Native SDKs (OpenAI, Anthropic, etc.) | No native SDKs; must call REST APIs |
| **JSON handling** | Native dicts, `json` module | `ConvertFrom-Json` works but clunkier |
| **MKV metadata** | `pymediainfo`, `subprocess` calls | `subprocess` calls only |
| **Community tools** | Extensive (FileBot, MKV Episode Matcher, etc.) | Very limited |
| **Cross-platform** | Yes | Yes (PowerShell Core), but ecosystem is Windows-centric |
| **Interactive prompts** | `input()`, `questionary`, `rich` | `Read-Host`, basic |
| **Existing ecosystem** | Existing tools like `jellyfin-renamer`, `mkv-episode-matcher` | None found |

### 5.2 Recommendation: **Hybrid — Python Core + PowerShell Wrapper** 🐍🔷

**Python** handles the heavy lifting because:

1. **LLM SDKs** — OpenAI, Anthropic, and others have first-class Python SDKs
2. **TMDb libraries** — `tmdbv3api` provides ready-made API bindings
3. **Rich CLI UX** — Libraries like `rich` and `questionary` make beautiful interactive prompts
4. **MediaInfo** — `pymediainfo` wraps MediaInfo for direct Python access
5. **Community** — Existing open-source tools (MKV Episode Matcher, AutoTag) are Python-based
6. **Maintainability** — Easier for complex logic (matching algorithms, fuzzy search)

**PowerShell** provides the entry-point wrapper (`rename-media.ps1`) because:

1. **Consistency** — Matches the existing `process-dvds.ps1` scripts for a unified workflow
2. **Convenience** — Handles path validation, Python venv setup, and argument passing
3. **Familiarity** — Keeps the user experience in the same shell environment

**Note:** The existing `process-dvds.ps1` scripts remain in PowerShell (they work fine for MakeMKV automation). The new renamer tool adds a thin PowerShell wrapper around a Python application.

---

## 6. LLM Integration Strategy

### 6.1 Role of the LLM

The LLM acts as an intelligent "media librarian" that:
1. **Interprets disc/folder names** — Parses cryptic disc labels like `FRIENDS_S2_D3` into structured queries ("Friends, Season 2, Disc 3")
2. **Matches files to episodes** — Given episode runtimes from TMDb and file durations from MediaInfo, proposes the most likely mapping
3. **Handles ambiguity** — When multiple matches are possible, explains its reasoning and asks the user to choose
4. **Formats output** — Generates Plex-compliant filenames

### 6.2 Proposed LLM Workflow

```
Input to LLM:
  - Folder name: "BAND_OF_BROTHERS_D2"
  - Files: [t00.mkv (58min), t01.mkv (52min), t02.mkv (61min)]
  - TMDb data: Band of Brothers S01E01 (94min), S01E02 (70min), ...
  - TMDb data: Band of Brothers S01E04 (58min), S01E05 (52min), S01E06 (61min)

LLM Response:
  "Based on the folder name and duration matching, this appears to be
   Band of Brothers Disc 2 containing episodes 4-6:
   - t00.mkv (58min) → S01E04 'Replacements' (58min)
   - t01.mkv (52min) → S01E05 'Crossroads' (52min)
   - t02.mkv (61min) → S01E06 'Bastogne' (61min)
   Confidence: High (durations match within 2 minutes)"
```

### 6.3 API Options

| Provider | Model | Cost | Notes |
|----------|-------|------|-------|
| **OpenAI** | GPT-4o / GPT-4o-mini | $2.50-$10/M tokens | Best balance of cost and quality |
| **Anthropic** | Claude Sonnet | ~$3/M tokens | Excellent at structured reasoning |
| **Local** | Ollama + Llama 3 | Free | Slower, requires GPU, but zero API cost |

**Recommendation:** Start with **OpenAI GPT-4o-mini** (cheapest, fast, plenty smart for this task). Allow configuration to swap providers.

---

## 7. Content Identification Strategy

### 7.1 Step-by-Step Matching Algorithm

1. **Parse folder name** — Use LLM to extract likely title, season, disc number from the folder name
2. **Search TMDb** — Query for matching movies or TV shows
3. **Classify content type:**
   - **Movie:** 1 long file (>60min) + short bonus clips → match to movie
   - **TV Series:** Multiple files of similar length (20-60min each) → match to episodes
   - **Ambiguous:** Ask user
4. **Duration matching (TV):**
   - Get episode runtimes from TMDb for the identified season
   - Match MKV durations to episode runtimes (allowing ±3 min tolerance)
   - Order matters — episodes on a disc are typically sequential
5. **LLM arbitration** — If algorithmic matching is ambiguous, present the data to the LLM for a reasoned best-guess
6. **User confirmation** — Always show proposed mappings and ask user to confirm before renaming

### 7.2 Handling Edge Cases

| Edge Case | Strategy |
|-----------|----------|
| Multi-disc TV sets | Track disc numbers; map episodes sequentially across discs |
| Special features | Filter by duration (< 10min = likely bonus content) |
| Extended/Director's cuts | Flag files with durations significantly longer than theatrical |
| Multi-part episodes | Check TMDb for multi-episode entries |
| Disc label is gibberish | Fall back to LLM interpretation + user input |
| No TMDb match | Prompt user to manually enter the title |

---

## 8. Plex Naming Conventions

### 8.1 Movies

```
/Movies/
  /Movie Name (Year)/
    Movie Name (Year).mkv
```

Example: `/Movies/The Matrix (1999)/The Matrix (1999).mkv`

With TMDb ID for better matching:
```
/Movies/The Matrix (1999) {tmdb-603}/The Matrix (1999) {tmdb-603}.mkv
```

### 8.2 TV Shows

```
/TV Shows/
  /Show Name (Year)/
    /Season 01/
      Show Name (Year) - s01e01 - Episode Title.mkv
      Show Name (Year) - s01e02 - Episode Title.mkv
```

Example: `/TV Shows/Band of Brothers (2001)/Season 01/Band of Brothers (2001) - s01e04 - Replacements.mkv`

### 8.3 Specials

```
/TV Shows/Show Name (Year)/Season 00/Show Name (Year) - s00e01 - Special Title.mkv
```

---

## 9. Existing Tools & Prior Art

| Tool | Language | Relevance |
|------|----------|-----------|
| **MKV Episode Matcher** | Python | Most similar; matches MKV files to episodes using subtitles/speech recognition |
| **FileBot** | Java | Industry standard renamer; paid license ($6/yr); scriptable |
| **AutoTag** | .NET | CLI tool for tagging MKV/MP4 from TMDb |
| **jellyfin-renamer** | Python | Renames for Jellyfin/Plex standards |
| **Sonarr/Radarr** | .NET | Full automation suites (overkill for our use case) |

**Key differentiator of our tool:** Using LLM intelligence to interpret disc labels and make smart matches, with interactive user confirmation — none of the existing tools do this.

---

## 10. Recommended Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Media Renamer CLI                  │
│                    (Python 3.12+)                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │   Scanner    │  │  LLM Engine  │  │  Renamer   │ │
│  │  MediaInfo   │  │  OpenAI /    │  │  File ops  │ │
│  │  + folder    │  │  Anthropic   │  │  + Plex    │ │
│  │  analysis    │  │  + prompts   │  │  naming    │ │
│  └──────┬──────┘  └──────┬───────┘  └─────┬──────┘ │
│         │                │                │         │
│  ┌──────┴──────┐  ┌──────┴───────┐  ┌─────┴──────┐ │
│  │ TMDb API    │  │   User       │  │  Output    │ │
│  │ OMDb API    │  │   Prompts    │  │  Staging   │ │
│  │ (metadata)  │  │   (confirm)  │  │  Directory │ │
│  └─────────────┘  └──────────────┘  └────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 11. Key Python Dependencies

| Package | Purpose |
|---------|---------|
| `tmdbv3api` | TMDb API client |
| `pymediainfo` | MKV metadata extraction |
| `openai` | LLM API calls |
| `rich` | Beautiful terminal output, tables, progress bars |
| `questionary` | Interactive user prompts (confirmations, selections) |
| `click` or `typer` | CLI framework |
| `pydantic` | Data models for media items |
| `python-dotenv` | API key management |

---

## References

- [TMDb API Documentation](https://developer.themoviedb.org/)
- [Plex Movie Naming](https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/)
- [Plex TV Show Naming](https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/)
- [MediaInfo CLI](https://mediaarea.net/en/MediaInfo)
- [MKV Episode Matcher](https://github.com/Jsakkos/mkv-episode-matcher)
- [MakeMKV Naming Templates](https://forum.makemkv.com/forum/viewtopic.php?t=18313)
- [OMDb API](https://www.omdbapi.com/)
- [TheTVDB API](https://thetvdb.com/api-information)
