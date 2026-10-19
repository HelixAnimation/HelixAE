param(
    [Parameter(Mandatory = $true)][string]$InputDirectory,
    [Parameter(Mandatory = $true)][string]$OutputZxp,
    [string]$SigningRoot = "C:\secure\helixae-signing",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [switch]$NoTimestamp
)

$ErrorActionPreference = "Stop"

$InputDirectory = [IO.Path]::GetFullPath($InputDirectory)
$OutputZxp = [IO.Path]::GetFullPath($OutputZxp)
$SigningRoot = [IO.Path]::GetFullPath($SigningRoot)
$zxpsign = Join-Path $SigningRoot "ZXPSignCmd.exe"
$passwordFile = Join-Path $SigningRoot "password.txt"
$certificate = Join-Path $SigningRoot "helixae.p12"

foreach ($path in @($zxpsign, $passwordFile, $certificate)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Signing prerequisite missing: $path. Run tools/setup_signing.ps1 on the signing host."
    }
}
if (-not (Test-Path -LiteralPath $InputDirectory -PathType Container)) {
    throw "Panel input directory does not exist: $InputDirectory"
}

$outputDirectory = Split-Path -Parent $OutputZxp
if ($outputDirectory) {
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
}
if (Test-Path -LiteralPath $OutputZxp) {
    Remove-Item -LiteralPath $OutputZxp -Force
}

$password = [IO.File]::ReadAllText($passwordFile).Trim()
if (-not $password) {
    throw "Signing password file is empty: $passwordFile"
}

$arguments = @("-sign", $InputDirectory, $OutputZxp, $certificate, $password)
if (-not $NoTimestamp) {
    $arguments += @("-tsa", $TimestampUrl)
}

& $zxpsign @arguments
if ($LASTEXITCODE -ne 0) {
    throw "ZXPSignCmd -sign failed with exit code $LASTEXITCODE. Retry with -NoTimestamp if the timestamp server is unavailable."
}

$verifyOutput = & $zxpsign -verify $OutputZxp 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "ZXPSignCmd -verify failed with exit code ${LASTEXITCODE}: $($verifyOutput -join "`n")"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($OutputZxp)
try {
    $entry = $zip.GetEntry("META-INF/signatures.xml")
    if (-not $entry -or $entry.Length -eq 0) {
        throw "Signed package has no non-empty META-INF/signatures.xml"
    }
} finally {
    $zip.Dispose()
}

Write-Output "SIGNED_OK $OutputZxp"
