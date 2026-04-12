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

    $makemkvPath = """C:\Program Files\MakeMKV\makemkvcon64.exe"""

    # Make sure the output directory exists
    if (-not (Test-Path -Path $directoryForOutput -PathType Container ))
    {
        New-Item -Path $directoryForOutput -ItemType Directory | Out-Null
    }

    Write-Host "------------------------------------------------------------------------------------"
    Write-Host "------------------------------------------------------------------------------------"
    Write-Host "---"
    Write-Host "---"
    Write-Host "---  STARTING $fileToProcess : "
    Write-Host "---"
    Write-Host "---"
    Write-Host "------------------------------------------------------------------------------------"
    Write-Host "------------------------------------------------------------------------------------"

    # Run "foo.exe" with the specified parameters
    # $process = Start-Process -FilePath $makemkvPath -ArgumentList "mkv", $fileToProcess, "all", $directoryForOutput -NoNewWindow -Wait -RedirectStandardOutput $null -RedirectStandardError $null
	$pinfo = New-Object System.Diagnostics.ProcessStartInfo
	$pinfo.FileName = $makemkvPath
	$pinfo.Arguments = @("mkv", """$fileToProcess""", "all", """$directoryForOutput""")
	$pinfo.RedirectStandardError = $false
	$pinfo.RedirectStandardOutput = $false
	$pinfo.UseShellExecute = $false
	$proc = New-Object System.Diagnostics.Process
	$proc.StartInfo = $pinfo
	$proc.Start() | Out-Null
	$proc.WaitForExit()

    # Check the exit code to determine success or failure
    Write-Host "------------------------------------------------------------------------------------"
    Write-Host "------------------------------------------------------------------------------------"
    Write-Host "---"
    Write-Host "---"
    if ($proc.ExitCode -eq 0) 
    {
        Write-Host "---  SUCCESS $fileToProcess : "
        $returnValue = $true
    } 
    else 
    {
        Write-Host "---  FAILURE $fileToProcess : "
        $returnValue = $false
    }
    Write-Host "---"
    Write-Host "---"
    Write-Host "------------------------------------------------------------------------------------"
    Write-Host "------------------------------------------------------------------------------------"

    # Tidy Up
    $proc.Close()
    return $returnValue
}


# Create lists for successful and failed attempts
$successFileList = @()
$failureFileList = @()

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
        # Write-Host "    Found ISO file: $isoFile"
        $isoFileRootName = [System.IO.Path]::GetFileNameWithoutExtension($isoFile)
        $directoryForISOOutput = Join-Path -Path $outputDirectory -ChildPath $isoFileRootName
        $isoFileToProcess = Join-Path -Path $inputDirectory -ChildPath $isoFile
        # Check it
        $result = Run-MakeMKV  $isoFileToProcess  $directoryForISOOutput
        # Write-Host "         To Directory: $directoryForISOOutput"
        if ($result)
        {
            $successFileList += $isoFileToProcess
        }
        else 
        {
            $failureFileList += $isoFileToProcess
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
            # Write-Host "Found index.bdmv: $indexBDMVFile"
            $indexFileRootName = (Get-Item (Join-Path $indexBDMVFile "..\..")).Name
            $directoryForIndexOutput = Join-Path -Path $outputDirectory -ChildPath $indexFileRootName
            # Check it
            $result = Run-MakeMKV  $indexBDMVFile  $directoryForIndexOutput
            # Write-Host "         To Directory: $directoryForIndexOutput"
            if ($result)
            {
                $successFileList += $indexBDMVFile
            }
            else 
            {
                $failureFileList += $indexBDMVFile
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

#  Now output some summary for ease of reading
Write-Host ""
Write-Host ""
Write-Host "------------------------------------------------------------------------------------"
Write-Host "------------------------------------------------------------------------------------"
Write-Host "---"
Write-Host "---"
if ($successFileList.Count -gt 0)
{
    Write-Host "---     List of SUCCESSFULL Processed Files"
    Write-Host "---"
    foreach($successFile in $successFileList)
    {
        Write-Host "---         - $successFile"
    }
}
else 
{
    Write-Host "---     ZERO SUCCESSFULL Processed Files"
}
Write-Host "---"
Write-Host "------------------------------------------------------------------------------------"
Write-Host "------------------------------------------------------------------------------------"
Write-Host ""
Write-Host ""
Write-Host ""

Write-Host "------------------------------------------------------------------------------------"
Write-Host "------------------------------------------------------------------------------------"
Write-Host "---"
Write-Host "---"
if ($failureFileList.Count -gt 0)
{
    Write-Host "---     List of FAILED Processed Files"
    Write-Host "---"
    foreach($failureFile in $failureFileList)
    {
        Write-Host "---         - $failureFile"
    }
}
else 
{
    Write-Host "---     ZERO FAILED Processed Files"
}
Write-Host "---"
Write-Host "------------------------------------------------------------------------------------"
Write-Host "------------------------------------------------------------------------------------"
Write-Host ""
Write-Host ""
Write-Host ""

Write-Host "Processing completed."
