param([Parameter(Mandatory=$true)][string]$PackageRoot)
$ErrorActionPreference = 'Stop'
$package = (Resolve-Path -LiteralPath $PackageRoot).Path
$project = Split-Path $PSScriptRoot -Parent
$release = Get-Content -LiteralPath (Join-Path $package 'release.json') -Raw | ConvertFrom-Json
$testRoot = Join-Path $project ('outputs\完整安装验收-' + [guid]::NewGuid().ToString('N'))
$target = Join-Path $testRoot '安装目录'
$env:ETOPO_STATE_DIR = Join-Path $testRoot 'user-profile'
$link = Join-Path ([Environment]::GetFolderPath('Desktop')) "ETOPO2022 Analyzer $($release.version).lnk"
if (Test-Path -LiteralPath $link) { throw 'An existing desktop shortcut was left unchanged. Remove this test conflict before running.' }
New-Item -ItemType Directory -Path $testRoot | Out-Null
function Assert($Value, $Message) { if (-not $Value) { throw $Message } }
function Install-Checked($Log) {
    # Windows PowerShell 将原生 stderr 警告包装为错误记录；结果以退出码为准。
    $ErrorActionPreference = 'Continue'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'Install.ps1') -Destination $target *> (Join-Path $testRoot $Log)
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    Assert ($code -eq 0) "Installation failed; see $testRoot\$Log"
}
Install-Checked 'install.log'
'user-owned output' | Set-Content -LiteralPath (Join-Path $target '用户成果.csv') -Encoding UTF8
'# damaged for repair test' | Set-Content -LiteralPath (Join-Path $target 'main.py') -Encoding UTF8
Install-Checked 'repair.log'
Assert ((Get-FileHash -LiteralPath (Join-Path $target 'main.py')).Hash -eq (Get-FileHash -LiteralPath (Join-Path $package 'main.py')).Hash) 'Damaged application was not repaired'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
Assert ($shortcut.TargetPath -eq (Join-Path $target 'Launcher.exe')) 'Wrong shortcut target'
. (Join-Path $package 'InstallCommon.ps1')
$key = Get-UninstallKey $target
Assert ((Get-ItemProperty -Path $key).DisplayVersion -eq $release.version) 'Wrong uninstall version'
$visibleReport = Join-Path $testRoot 'visible.json'
$process = Start-Process -FilePath $shortcut.TargetPath -ArgumentList "Demo --verify-window `"$visibleReport`"" -WindowStyle Hidden -PassThru
Assert ($process.WaitForExit(45000)) 'Visible GUI timed out'
Assert ($process.ExitCode -eq 0) 'Visible GUI failed'
$visible = Get-Content -LiteralPath $visibleReport -Raw | ConvertFrom-Json
Assert ($visible.passed -and $visible.version -eq $release.version) 'Wrong visible version'
Copy-Item -LiteralPath (Join-Path $target 'installation-check.json') -Destination (Join-Path $testRoot 'self-check.json')
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $target 'Uninstall.ps1') -Quiet *> (Join-Path $testRoot 'uninstall.log')
Assert ($LASTEXITCODE -eq 0) 'Uninstall failed'
Assert (-not (Test-Path -Path $key)) 'Uninstall registration retained'
Assert (-not (Test-Path -LiteralPath $link)) 'Shortcut retained'
$remaining = @(Get-ChildItem -LiteralPath $target -Force)
Assert ($remaining.Count -eq 1 -and $remaining[0].Name -eq '用户成果.csv') 'Program files, hidden files or empty package directories remain'
Assert ((Get-Content -LiteralPath $remaining[0].FullName -Raw).Trim() -eq 'user-owned output') 'User data changed'
$report = @{passed=$true; version=$release.version; root=$testRoot; checks=@('chinese-path-install','corruption-repair','desktop-shortcut','registry-version','native-window','uninstall','only-user-file-retained')}
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testRoot 'result.json') -Encoding UTF8
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $project 'outputs/rc2-full-installer-latest.json') -Encoding UTF8
Write-Host "Full installer checks passed: $testRoot"
