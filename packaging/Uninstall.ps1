param([switch]$Quiet)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'InstallCommon.ps1')
    $root = Get-InstallRoot $PSScriptRoot
    $state = Get-Content -LiteralPath (Join-Path $root 'installation.json') -Raw | ConvertFrom-Json
    if ($state.product -ne 'ETOPO2022 Analyzer' -or $state.root -ne $root -or -not $state.files) { throw 'Not a managed installation. No files were removed.' }
    if (-not $Quiet) {
        Add-Type -AssemblyName System.Windows.Forms
        $answer = [Windows.Forms.MessageBox]::Show("卸载 ETOPO2022 Analyzer $($state.version)？`n`n安装位置：$root`n保留用户输出、数据和工作状态文件。", '确认卸载', 'YesNo', 'Question', 'Button2')
        if ($answer -ne 'Yes') { exit 0 }
    }
    Assert-AppStopped $root
    # 先校验完整清单，再删除已登记文件；不递归删除安装目录或用户目录。
    $paths = @($state.files | ForEach-Object { Get-OwnedPath $root $_ })
    $paths += Get-OwnedPath $root 'installation-check.json'
    $directories = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($directory in $state.directories) { $null = $directories.Add((Get-OwnedPath $root $directory)) }
    foreach ($path in $paths) {
        $parent = Split-Path $path -Parent
        while ($parent -and $parent.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { $null = $directories.Add($parent); $parent = Split-Path $parent -Parent }
    }
    # 卸载脚本与安装标记留到最后，失败后仍可重试。
    $controlFiles = @('Uninstall.ps1','Uninstall.cmd','InstallCommon.ps1')
    foreach ($path in $paths) {
        if ((Split-Path $path -Leaf) -notin $controlFiles -and (Test-Path -LiteralPath $path -PathType Leaf)) { Remove-Item -LiteralPath $path -Force }
    }
    foreach ($link in $state.shortcuts) {
        if (Test-Path -LiteralPath $link -PathType Leaf) {
            $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
            if ($shortcut.TargetPath -eq (Join-Path $root 'Launcher.exe')) { Remove-Item -LiteralPath $link -Force }
        }
    }
    $key = Get-UninstallKey $root
    if ((Get-ItemProperty -Path $key -ErrorAction SilentlyContinue).InstallLocation -eq $root) { Remove-Item -LiteralPath $key }
    foreach ($file in $controlFiles) { $path = Get-OwnedPath $root $file; if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }
    Remove-Item -LiteralPath (Join-Path $root 'installation.json') -Force
    foreach ($directory in ($directories | Sort-Object Length -Descending)) {
        if ((Test-Path -LiteralPath $directory) -and -not (Get-ChildItem -LiteralPath $directory -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $directory }
    }
    if (-not (Get-ChildItem -LiteralPath $root -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $root }
    Write-Host 'Uninstalled. User outputs and untracked files were retained.'
} catch {
    Write-Error $_ -ErrorAction Continue
    if (-not $Quiet) { Add-Type -AssemblyName System.Windows.Forms; [Windows.Forms.MessageBox]::Show($_.Exception.Message, '卸载未完成') | Out-Null }
    exit 1
}
