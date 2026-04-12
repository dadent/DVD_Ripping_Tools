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

### 2. Media Renamer (Coming Soon)

An intelligent CLI tool that automatically identifies and renames MKV files produced by MakeMKV, organizing them into a Plex-ready folder structure.

**Key features (planned):**
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

## Typical Workflow

```
1. Rip DVDs/Blu-rays     →  process-dvds.ps1 (MakeMKV automation)
2. Identify & rename      →  Media Renamer (coming soon)
3. Move to Plex library   →  (handled by Media Renamer staging)
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
