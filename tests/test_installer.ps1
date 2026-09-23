param([string]$TestRoot)
$ErrorActionPreference = 'Stop'
if (-not $TestRoot) { $TestRoot = Join-Path (Split-Path $PSScriptRoot -Parent) ('outputs\installer-test-' + [guid]::NewGuid().ToString('N')) }
$root = [IO.Path]::GetFullPath($TestRoot)
$source = Join-Path $root 'source package'
$target = Join-Path $root 'installed app'
$packaging = Join-Path (Split-Path $PSScriptRoot -Parent) 'packaging'
New-Item -ItemType Directory -Path (Join-Path $source 'src/etopo_analyzer') -Force | Out-Null
foreach ($name in @('Install.ps1','InstallCommon.ps1','Uninstall.ps1','Uninstall.cmd')) { Copy-Item -LiteralPath (Join-Path $packaging $name) -Destination $source }
'VERSION = "1.0.0-rc2"' | Set-Content -LiteralPath (Join-Path $source 'src/etopo_analyzer/version.py') -Encoding UTF8
'{"product":"ETOPO2022 Analyzer","version":"1.0.0-rc2","unpacked_bytes":1024}' | Set-Content -LiteralPath (Join-Path $source 'release.json') -Encoding UTF8
'original application' | Set-Content -LiteralPath (Join-Path $source 'Launcher.exe') -Encoding ASCII
New-Item -ItemType Directory -Path (Join-Path $source 'empty-cache') | Out-Null
$hidden = Join-Path $source 'hidden-runtime.dat'
'packaged hidden data' | Set-Content -LiteralPath $hidden
(Get-Item -LiteralPath $hidden).Attributes = [IO.FileAttributes]::Hidden
@'
param($Mode, $Report)
if ($env:ETOPO_INSTALL_TEST_FAIL -eq '1') { exit 1 }
'{"passed":true}' | Set-Content -LiteralPath $Report -Encoding UTF8
'@ | Set-Content -LiteralPath (Join-Path $source 'Launch.ps1') -Encoding UTF8
. (Join-Path $packaging 'InstallCommon.ps1')
function Assert($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Install-Test([int]$Expected) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $source 'Install.ps1') -Destination $target -NoShortcuts
    Assert ($LASTEXITCODE -eq $Expected) "Install exit code expected $Expected, got $LASTEXITCODE"
}
# Simulated self-check failure must leave an identifiable, retryable installation.
$env:ETOPO_INSTALL_TEST_FAIL = '1'
Install-Test 1
$state = Get-Content -LiteralPath (Join-Path $target 'installation.json') -Raw | ConvertFrom-Json
Assert ($state.status -eq 'incomplete') 'Missing incomplete state'
Remove-Item Env:ETOPO_INSTALL_TEST_FAIL
Install-Test 0
$key = Get-UninstallKey $target
Assert ((Get-ItemProperty -Path $key).DisplayVersion -eq '1.0.0-rc2') 'Uninstall registration/version missing'
# Damaged files of equal size/time must be replaced; user files must survive.
$program = Join-Path $target 'Launcher.exe'
$stamp = (Get-Item -LiteralPath $program).LastWriteTime
'damaged! application' | Set-Content -LiteralPath $program -Encoding ASCII
(Get-Item -LiteralPath $program).LastWriteTime = $stamp
$userFile = Join-Path $target 'my-results.csv'
'user data' | Set-Content -LiteralPath $userFile
Install-Test 0
Assert ((Get-FileHash -LiteralPath $program).Hash -eq (Get-FileHash -LiteralPath (Join-Path $source 'Launcher.exe')).Hash) 'Repair did not replace damaged file'
Assert (Test-Path -LiteralPath $userFile) 'Repair removed user data'
# Version mismatch must not repair or replace an existing installation.
$versionFile = Join-Path $source 'src/etopo_analyzer/version.py'
'VERSION = "9.9.9"' | Set-Content -LiteralPath $versionFile -Encoding UTF8
Install-Test 1
'VERSION = "1.0.0-rc2"' | Set-Content -LiteralPath $versionFile -Encoding UTF8
# No adoption of arbitrary folders and no source/destination overlap.
$unmanaged = Join-Path $root 'unmanaged'
New-Item -ItemType Directory -Path $unmanaged | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $source 'Install.ps1') -Destination $unmanaged -NoShortcuts
Assert ($LASTEXITCODE -ne 0) 'Unmanaged folder accepted'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $source 'Install.ps1') -Destination $source -NoShortcuts
Assert ($LASTEXITCODE -ne 0) 'Source overwritten'
# Reject a malicious traversal before deleting any program file.
$marker = Join-Path $target 'installation.json'
$original = Get-Content -LiteralPath $marker -Raw
$state = $original | ConvertFrom-Json
$state.files += '..\outside.txt'
$state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $marker -Encoding UTF8
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $target 'Uninstall.ps1') -Quiet
Assert ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $program)) 'Unsafe uninstall was not rejected atomically'
$original | Set-Content -LiteralPath $marker -Encoding UTF8
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $target 'Uninstall.ps1') -Quiet
Assert ($LASTEXITCODE -eq 0) 'Uninstall failed'
Assert (-not (Test-Path -LiteralPath $program)) 'Program was not removed'
Assert (-not (Test-Path -Path $key)) 'Uninstall entry was not removed'
Assert ((Get-Content -LiteralPath $userFile -Raw).Trim() -eq 'user data') 'User data was removed'
Assert (Test-Path -LiteralPath (Join-Path $source 'Install.ps1')) 'Original package was removed'
# Empty installation directories can be removed completely and reinstalled.
$target = Join-Path $root 'clean installation'
Install-Test 0
$key = Get-UninstallKey $target
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $target 'Uninstall.ps1') -Quiet
Assert ($LASTEXITCODE -eq 0 -and -not (Test-Path -LiteralPath $target)) 'Empty installation directory was retained'
Assert (-not (Test-Path -Path $key)) 'Second uninstall entry retained'
@{passed=$true; root=$root; checks=@('failed-install-retry','repair-corruption','registry-version','version-mismatch','unmanaged-rejection','source-protection','traversal-rejection','uninstall','user-data-retained','empty-install-removal')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'result.json') -Encoding UTF8
Write-Host "Installer checks passed: $root"
