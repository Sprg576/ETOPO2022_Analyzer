param([string]$Destination, [switch]$NoShortcuts)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'InstallCommon.ps1')
    $sourceRoot = Get-InstallRoot $PSScriptRoot
    $release = Get-Content -LiteralPath (Join-Path $sourceRoot 'release.json') -Raw | ConvertFrom-Json
    if ($release.product -ne 'ETOPO2022 Analyzer' -or $release.version -notmatch '^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$') { throw 'Invalid release metadata.' }
    $versionText = Get-Content -LiteralPath (Join-Path $sourceRoot 'src/etopo_analyzer/version.py') -Raw
    if ($versionText -notmatch ('VERSION = "' + [regex]::Escape($release.version) + '"')) { throw 'Package version mismatch.' }
    if (-not $Destination) { $Destination = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) "Programs\ETOPO2022Analyzer\$($release.version)" }
    $target = Get-InstallRoot $Destination
    if ($target -eq $sourceRoot -or $target.StartsWith($sourceRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or $sourceRoot.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Source and destination must be separate directories. Repair using the original extracted package.' }
    Assert-AppStopped $target
    $statePath = Join-Path $target 'installation.json'
    $previous = $null
    if (Test-Path -LiteralPath $target) {
        if (-not (Test-Path -LiteralPath $statePath)) { throw 'Existing folder is not a managed installation; choose a new folder.' }
        $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($previous.product -ne $release.product -or $previous.version -ne $release.version -or $previous.root -ne $target) { throw 'Only the same version can be repaired here. Install another version in a separate folder.' }
    }
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($target))
    if ($drive.AvailableFreeSpace -lt ([long]$release.unpacked_bytes + 512MB)) { throw 'Not enough disk space.' }
    $files = @(Get-ChildItem -LiteralPath $sourceRoot -Recurse -Force -File | Where-Object {
        $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and $_.Name -notin @('installation.json','installation-check.json','installation.json.tmp')
    } | ForEach-Object { $_.FullName.Substring($sourceRoot.Length + 1) })
    $directories = @(Get-ChildItem -LiteralPath $sourceRoot -Recurse -Force -Directory | Where-Object {
        $_.FullName -notmatch '[\\/]__pycache__([\\/]|$)'
    } | ForEach-Object { $_.FullName.Substring($sourceRoot.Length + 1) })
    foreach ($file in $files) { $null = Get-OwnedPath $sourceRoot $file; $null = Get-OwnedPath $target $file }
    foreach ($directory in $directories) { $null = Get-OwnedPath $sourceRoot $directory; $null = Get-OwnedPath $target $directory }
    $state = [ordered]@{ product=$release.product; version=$release.version; root=$target; status='incomplete'; files=$files; directories=$directories; shortcuts=@() }
    if ($previous) { $state.shortcuts = @($previous.shortcuts) }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Write-InstallState $target $state
    Write-Host "Installing / repairing $($release.version): $target"
    & robocopy.exe $sourceRoot $target /E /IS /IT /IM /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD __pycache__ /XF installation.json installation-check.json installation.json.tmp
    if ($LASTEXITCODE -ge 8) { throw 'Copy failed. Run Install.cmd again to repair this installation.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $target 'Launch.ps1') -Mode Check -Report (Join-Path $target 'installation-check.json')
    if ($LASTEXITCODE -ne 0) { throw 'Self-check failed. Keep the original package and run Install.cmd again to repair.' }
    $check = Get-Content -LiteralPath (Join-Path $target 'installation-check.json') -Raw | ConvertFrom-Json
    if (-not $check.passed) { throw 'Self-check did not pass.' }
    if (-not $NoShortcuts) {
        $shell = New-Object -ComObject WScript.Shell
        $link = Join-Path ([Environment]::GetFolderPath('Desktop')) "ETOPO2022 Analyzer $($release.version).lnk"
        $shortcut = $shell.CreateShortcut($link)
        $shortcut.TargetPath = Join-Path $target 'Launcher.exe'
        $shortcut.Arguments = 'Run'
        $shortcut.WorkingDirectory = $target
        $shortcut.IconLocation = Join-Path $target 'runtime\apps\qgis-ltr\doc\favicon.ico'
        $shortcut.Save()
        $state.shortcuts = @($link)
    }
    $state.status = 'installed'
    Write-InstallState $target $state
    $key = Get-UninstallKey $target
    New-Item -Path $key -Force | Out-Null
    $properties = @{ DisplayName="ETOPO2022 Analyzer $($release.version)"; DisplayVersion=$release.version; Publisher='ETOPO2022 Analyzer'; InstallLocation=$target;
        UninstallString="powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$target\Uninstall.ps1`"";
        QuietUninstallString="powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$target\Uninstall.ps1`" -Quiet" }
    foreach ($name in $properties.Keys) { New-ItemProperty -Path $key -Name $name -Value $properties[$name] -PropertyType String -Force | Out-Null }
    foreach ($name in @('NoModify','NoRepair')) { New-ItemProperty -Path $key -Name $name -Value 1 -PropertyType DWord -Force | Out-Null }
    Write-Host 'Installation passed. Use the desktop shortcut to start; run Install.cmd from the original package to repair.'
    Write-Host 'Uninstall from Windows Installed apps or Uninstall.cmd. User outputs are retained.'
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
