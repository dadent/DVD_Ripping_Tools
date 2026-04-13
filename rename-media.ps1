<#
.SYNOPSIS
    Renames MakeMKV output files into a Plex-ready folder structure.

.DESCRIPTION
    Thin PowerShell wrapper around the Python-based Media Renamer tool.
    Handles Python virtual-environment setup and argument forwarding.

.PARAMETER Source
    Source directory containing MakeMKV output folders.

.PARAMETER Dest
    Destination / staging directory for Plex-ready output.

.PARAMETER DryRun
    Preview actions without moving or renaming any files.

.PARAMETER ConfigFile
    Path to config.yaml (default: ./config.yaml).

.EXAMPLE
    .\rename-media.ps1 -Source "E:\MakeMKV_Output" -Dest "E:\PlexStaging"
    .\rename-media.ps1 -Source "E:\MakeMKV_Output" -Dest "E:\PlexStaging" -DryRun
#>
param (
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Dest,

    [switch]$DryRun,

    [string]$ConfigFile
)

# --- Resolve paths -----------------------------------------------------------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$venvDir   = Join-Path $scriptDir ".venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$pipExe    = Join-Path $venvDir "Scripts\pip.exe"

# --- Validate source directory ------------------------------------------------
if (-not (Test-Path -Path $Source -PathType Container)) {
    Write-Error "Source directory not found: $Source"
    exit 1
}

# --- Ensure Python virtual environment exists ---------------------------------
if (-not (Test-Path -Path $pythonExe)) {
    Write-Host "Creating Python virtual environment in $venvDir ..."
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment. Is Python 3.12+ installed?"
        exit 1
    }

    Write-Host "Installing dependencies ..."
    & $pipExe install --quiet -e $scriptDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install dependencies."
        exit 1
    }
}

# --- Build arguments for the Python CLI ---------------------------------------
$pyArgs = @("--source", $Source, "--dest", $Dest)

if ($DryRun) {
    $pyArgs += "--dry-run"
}

if ($ConfigFile) {
    $pyArgs += @("--config", $ConfigFile)
}

# --- Run the tool -------------------------------------------------------------
& $pythonExe -m media_renamer.cli @pyArgs
exit $LASTEXITCODE
