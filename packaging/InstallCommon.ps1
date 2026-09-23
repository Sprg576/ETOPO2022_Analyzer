$ErrorActionPreference = 'Stop'
function Get-InstallRoot([string]$Path) {
    $root = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    if ($root -eq [IO.Path]::GetPathRoot($root).TrimEnd('\')) { throw 'A drive root cannot be an installation directory.' }
    Assert-NoLink $root
    return $root
}
function Assert-NoLink([string]$Path) {
    $item = $Path
    while ($item) {
        if ([IO.File]::Exists($item) -or [IO.Directory]::Exists($item)) {
            if ([IO.File]::GetAttributes($item) -band [IO.FileAttributes]::ReparsePoint) { throw "Linked paths are not supported: $item" }
        }
        $item = [IO.Path]::GetDirectoryName($item)
    }
}
function Get-OwnedPath([string]$Root, [string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)' -or $Relative.Contains(':')) { throw 'Invalid installation file path.' }
    $path = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    if (-not $path.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'File is outside the installation directory.' }
    Assert-NoLink $path
    return $path
}
function Get-UninstallKey([string]$Root) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $id = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant()))).Replace('-','').Substring(0,16) }
    finally { $sha.Dispose() }
    return "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ETOPO2022Analyzer-$id"
}
function Assert-AppStopped([string]$Root) {
    $running = Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)
    }
    if ($running) { throw 'Close ETOPO2022 Analyzer before installing, repairing or uninstalling.' }
}
function Write-InstallState([string]$Root, $State) {
    $temporary = Join-Path $Root 'installation.json.tmp'
    $State | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination (Join-Path $Root 'installation.json') -Force
}
