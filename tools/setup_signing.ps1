param(
    [string]$SigningRoot = "C:\secure\helixae-signing",
    [string]$CountryCode = "US",
    [string]$StateOrProvince = "New York",
    [string]$Organization = "Helix Animation",
    [string]$CommonName = "HelixAE",
    [int]$ValidityDays = 3650,
    [string]$ZXPSignCmdUrl = "https://raw.githubusercontent.com/Adobe-CEP/CEP-Resources/master/ZXPSignCMD/4.1.3/x64/ZXPSignCmd.exe",
    [string]$ExpectedSha256 = "ffc2223167225ce61d024eb463fc5ad1a1be16133f99ef334a646f7311916c98",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Restrict-ToCurrentUser {
    param([Parameter(Mandatory = $true)][string]$Path)

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    if (Test-Path -LiteralPath $Path -PathType Container) {
        $inheritance = [Security.AccessControl.InheritanceFlags]"ContainerInherit, ObjectInherit"
        $propagation = [Security.AccessControl.PropagationFlags]::None
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $identity, "FullControl", $inheritance, $propagation, "Allow"
        )
    } else {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $identity, "FullControl", "Allow"
        )
    }
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$SigningRoot = [IO.Path]::GetFullPath($SigningRoot)
New-Item -ItemType Directory -Force -Path $SigningRoot | Out-Null
Restrict-ToCurrentUser -Path $SigningRoot

$zxpsign = Join-Path $SigningRoot "ZXPSignCmd.exe"
$passwordFile = Join-Path $SigningRoot "password.txt"
$certificate = Join-Path $SigningRoot "helixae.p12"

if ($Force -and (Test-Path -LiteralPath $zxpsign)) {
    Remove-Item -LiteralPath $zxpsign -Force
}
if (-not (Test-Path -LiteralPath $zxpsign)) {
    Invoke-WebRequest -UseBasicParsing -Uri $ZXPSignCmdUrl -OutFile $zxpsign
}

$actualSha256 = Get-Sha256 -Path $zxpsign
if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
    throw "ZXPSignCmd SHA-256 mismatch. Expected $ExpectedSha256, got $actualSha256"
}
Restrict-ToCurrentUser -Path $zxpsign

if (Test-Path -LiteralPath $passwordFile) {
    $password = [IO.File]::ReadAllText($passwordFile).Trim()
    if (-not $password) {
        throw "Signing password file is empty: $passwordFile"
    }
} else {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    $password = [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
    [IO.File]::WriteAllText($passwordFile, $password, (New-Object Text.UTF8Encoding($false)))
    Restrict-ToCurrentUser -Path $passwordFile
}

if (-not (Test-Path -LiteralPath $certificate)) {
    & $zxpsign -selfSignedCert $CountryCode $StateOrProvince $Organization $CommonName $password $certificate -validityDays $ValidityDays
    if ($LASTEXITCODE -ne 0) {
        throw "ZXPSignCmd -selfSignedCert failed with exit code $LASTEXITCODE"
    }
    Restrict-ToCurrentUser -Path $certificate
}

$smokeRoot = Join-Path $env:TEMP ("helixae-sign-smoke-" + [guid]::NewGuid().ToString("N"))
$smokeSource = Join-Path $smokeRoot "panel"
$smokeOutput = Join-Path $smokeRoot "smoke.zxp"
try {
    New-Item -ItemType Directory -Force -Path (Join-Path $smokeSource "CSXS") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $smokeSource "js") | Out-Null
    [IO.File]::WriteAllText((Join-Path $smokeSource "index.html"), "smoke", (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText((Join-Path $smokeSource "CSXS/manifest.xml"), "<manifest/>", (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText((Join-Path $smokeSource "js/main.js"), "// smoke", (New-Object Text.UTF8Encoding($false)))

    & $zxpsign -sign $smokeSource $smokeOutput $certificate $password
    if ($LASTEXITCODE -ne 0) {
        throw "ZXPSignCmd smoke signing failed with exit code $LASTEXITCODE"
    }
    & $zxpsign -verify $smokeOutput | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ZXPSignCmd smoke verification failed with exit code $LASTEXITCODE"
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($smokeOutput)
    try {
        $entry = $zip.GetEntry("META-INF/signatures.xml")
        if (-not $entry -or $entry.Length -eq 0) {
            throw "Smoke-signed package has no non-empty META-INF/signatures.xml"
        }
    } finally {
        $zip.Dispose()
    }
} finally {
    if (Test-Path -LiteralPath $smokeRoot) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force
    }
}

Write-Output "Signing setup ready."
Write-Output "Signing root: $SigningRoot"
Write-Output "ZXPSignCmd SHA-256: $actualSha256"
Write-Output "Certificate: $certificate"
Write-Output "Password file: $passwordFile"
