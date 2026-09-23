param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [string]$Version,
    [string]$OutputDirectory,
    [switch]$SkipArchive
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$versionSource = Get-Content -LiteralPath (Join-Path $projectRoot 'src/etopo_analyzer/version.py') -Raw
if ($versionSource -notmatch 'VERSION = "([0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9]+)?)"') { throw 'Invalid application version.' }
$appVersion = $Matches[1]
if ($Version -and $Version -ne $appVersion) { throw 'Build version must match src/etopo_analyzer/version.py.' }
$Version = $appVersion
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot 'dist' }
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
$runtime = (Resolve-Path -LiteralPath $RuntimeRoot).Path
$packageName = "ETOPO2022Analyzer-$Version-win64"
$packageRoot = Join-Path $outputRoot $packageName
if (Test-Path -LiteralPath $packageRoot) { throw "Release folder exists; choose another output directory: $packageRoot" }
if ($outputRoot.StartsWith($runtime + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Output cannot be inside runtime.' }
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
New-Item -ItemType Directory -Path $packageRoot | Out-Null
function Copy-Tree([string]$Source, [string]$Target) {
    & robocopy.exe $Source $Target /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD __pycache__ .git .vs /XF '*.pyc' '*.log'
    if ($LASTEXITCODE -ge 8) { throw "Copy failed: $Source" }
}
Write-Host 'Copying application and complete runtime...'
Copy-Tree (Join-Path $projectRoot 'src') (Join-Path $packageRoot 'src')
Copy-Tree $runtime (Join-Path $packageRoot 'runtime')
Copy-Item -LiteralPath (Join-Path $projectRoot 'main.py') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Launcher.cs') -Destination $packageRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$fileVersion = ($Version -split '-')[0] + '.0'
$versionInfo = Join-Path $packageRoot 'VersionInfo.cs'
"using System.Reflection;`n[assembly: AssemblyVersion(`"$fileVersion`")]`n[assembly: AssemblyFileVersion(`"$fileVersion`")]`n[assembly: AssemblyInformationalVersion(`"$Version`")]" | Set-Content -LiteralPath $versionInfo -Encoding UTF8
& $compiler /nologo /target:winexe /reference:System.Windows.Forms.dll "/out:$packageRoot\Launcher.exe" (Join-Path $PSScriptRoot 'Launcher.cs') $versionInfo
if ($LASTEXITCODE -ne 0) { throw 'Native launcher compilation failed.' }
foreach ($name in @('Launch.ps1', 'Install.ps1', 'InstallCommon.ps1', 'Uninstall.ps1', 'Uninstall.cmd', 'Start.cmd', 'StartDemo.cmd', 'Install.cmd', 'Check.cmd', 'README.txt', 'THIRD_PARTY.txt')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $packageRoot
}
(Get-Content -LiteralPath (Join-Path $packageRoot 'README.txt') -Raw -Encoding UTF8).Replace('@VERSION@', $Version) | Set-Content -LiteralPath (Join-Path $packageRoot 'README.txt') -Encoding UTF8
$env:ETOPO_STATE_DIR = Join-Path $outputRoot '_verification-profile'
$env:ETOPO_USER_DIR = Join-Path $env:ETOPO_STATE_DIR 'outputs'
foreach ($mode in @('BuildData', 'Check', 'SmokeGui')) {
    Write-Host "Verifying relocated package: $mode"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $packageRoot 'Launch.ps1') -Mode $mode -Report (Join-Path $outputRoot "$packageName-check.json")
    if ($LASTEXITCODE -ne 0) { throw "Release verification failed: $mode. No ZIP was published." }
}
foreach ($mode in @('Run', 'Demo')) {
    $visibleReport = Join-Path $outputRoot "$packageName-visible-$mode.json"
    $process = Start-Process -FilePath (Join-Path $packageRoot 'Launcher.exe') -ArgumentList "$mode --verify-window `"$visibleReport`"" -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) { throw "Visible window verification timed out: $mode (PID $($process.Id)). No ZIP was published." }
    if ($process.ExitCode -ne 0) { throw "Visible window verification failed: $mode. No ZIP was published." }
    $visible = Get-Content -LiteralPath $visibleReport -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $visible.passed -or -not $visible.native_visible) { throw "Window was not visible: $mode. No ZIP was published." }
}
$report = Get-Content -LiteralPath (Join-Path $outputRoot "$packageName-check.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$size = (Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Measure-Object Length -Sum).Sum
$release = [ordered]@{ product='ETOPO2022 Analyzer'; version=$Version; platform='Windows 10/11 x64';
    created_at=(Get-Date).ToUniversalTime().ToString('o'); runtime_versions=$report.versions;
    unpacked_bytes=[long]$size; data='Synthetic demo only; global DEM supplied separately';
    verification='Relocated runtime self-check, offscreen GUI, native visible Run/Demo windows; target-PC acceptance still required' }
$release | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $packageRoot 'release.json') -Encoding UTF8
if (-not $SkipArchive) {
    $archive = Join-Path $outputRoot "$packageName.zip"
    if (Test-Path -LiteralPath $archive) { throw "Archive exists: $archive" }
    Write-Host 'Creating offline ZIP (this may take several minutes)...'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($packageRoot, $archive, [IO.Compression.CompressionLevel]::Optimal, $true)
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    "$hash  $packageName.zip" | Set-Content -LiteralPath "$archive.sha256" -Encoding ASCII
    Write-Host "ZIP: $archive"
}
Write-Host "Release verified: $packageRoot"
@("Current version: $Version", "Package: $packageName", "Install: $packageName\Install.cmd", "Run: $packageName\Start.cmd", 'Older versions are retained as history.') | Set-Content -LiteralPath (Join-Path $outputRoot 'CURRENT.txt') -Encoding UTF8
