param (
    [string]$inputDirectory,
    [string]$outputDirectory
)


#
#  Function to process an ISO or Index file
#
function Run-MakeMKV {
    param( 
        [string] $fileToProcess,
        [string] $directoryForOutput 
    )

    $makemkvPath = """C:\Program Files (x86)\MakeMKV\makemkvcon64.exe"""

    # Make sure the output directory exists
    if (-not (Test-Path -Path $directoryForOutput -PathType Container ))
    {
        New-Item -Path $directoryForOutput -ItemType Directory | Out-Null
    }


    # Prepare the arguments for the MakeMKV process and execute it
    $logFile = Join-Path -Path $directoryForOutput -ChildPath "MakeMKV_Log.txt"
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
	$pinfo.FileName = $makemkvPath
	$pinfo.Arguments = @("mkv", """$fileToProcess""", "all", """$directoryForOutput""")
	$pinfo.RedirectStandardError = $true
	$pinfo.RedirectStandardOutput = $true
	$pinfo.UseShellExecute = $false
	$proc = New-Object System.Diagnostics.Process
	$proc.StartInfo = $pinfo
	$proc.Start() | Out-Null
    $standardOutput = $proc.StandardOutput.ReadToEnd()
    $standardError = $proc.StandardError.ReadToEnd()
    $standardOutput | Out-File -FilePath $logFile
    $standardError | Out-File -FilePath $logFile -Append
	$proc.WaitForExit()

    # Check the exit code to determine success or failure
    if ($proc.ExitCode -eq 0) 
    {
        $returnValue = $true
    } 
    else 
    {
        $returnValue = $false
    }

    # Tidy Up
    $proc.Close()
    $proc.Dispose()
    return $returnValue
}


# Check if the input directory exists
if (-not (Test-Path -Path $inputDirectory -PathType Container)) 
{
    Write-Host "Input directory does not exist: $inputDirectory"
    exit
}

# Create the output directory if it doesn't exist
if (-not (Test-Path -Path $outputDirectory -PathType Container)) 
{
    New-Item -Path $outputDirectory -ItemType Directory | Out-Null
    Write-Host "Output directory created: $outputDirectory"
}
else
{
    Write-Host "Output directory already exists, no need to create: $outputDirectory"
}

# Process .iso files in the input directory
$isoFiles = Get-ChildItem -Path $inputDirectory -Filter "*.iso"
if ($isoFiles.Count -gt 0) 
{
    Write-Host ""
    Write-Host "First processing ISO Files"
    Write-Host ""
    foreach ($isoFile in $isoFiles)
    {
        $isoFileRootName = [System.IO.Path]::GetFileNameWithoutExtension($isoFile)
        $directoryForISOOutput = Join-Path -Path $outputDirectory -ChildPath $isoFileRootName
        $isoFileToProcess = Join-Path -Path $inputDirectory -ChildPath $isoFile
        # Convert It
        Write-Host -NoNewline "    Processing $isoFileToProcess : "
        $result = Run-MakeMKV  $isoFileToProcess  $directoryForISOOutput
        if ($result)
        {
            Write-Host "SUCCESS"
        }
        else 
        {
            Write-Host "FAILED"
        }
    }
} 
else 
{
    Write-Host ""
    Write-Host "No .iso files found in $inputDirectory."
    Write-Host ""
}

# Process BDMV directories for index.bdmv files
$bdmvDirectories = Get-ChildItem -Path $inputDirectory -Directory -Filter "BDMV" -Recurse
if ($bdmvDirectories.Count -gt 0 )
{
    Write-Host ""
    Write-Host "Now processing index.bdmv Files"
    Write-Host ""
    foreach ($bdmvDirectory in $bdmvDirectories) {
        $indexBDMVFile = Join-Path $bdmvDirectory.FullName "index.bdmv"
        if (Test-Path -Path $indexBDMVFile -PathType Leaf) {
            $indexFileRootName = (Get-Item (Join-Path $indexBDMVFile "..\..")).Name
            $directoryForIndexOutput = Join-Path -Path $outputDirectory -ChildPath $indexFileRootName
            # Convert It
            Write-Host -NoNewline "    Processing $indexBDMVFile : "
            $result = Run-MakeMKV  $indexBDMVFile  $directoryForIndexOutput
            if ($result)
            {
                Write-Host "SUCCESS"
            }
            else 
            {
                Write-Host "FAILED"
            }
        }
    }
}
else
{
    Write-Host ""
    Write-Host "NO index.bdmv files found"
    Write-Host ""

}

Write-Host ""
Write-Host "Processing completed."
