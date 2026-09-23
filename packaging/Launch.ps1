param(
    [ValidateSet('Run', 'Demo', 'Check', 'SmokeGui', 'BuildData')][string]$Mode = 'Run',
    [string]$RuntimeRoot,
    [string]$Report,
    [switch]$VerifyWindow
)
$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
    if (-not $RuntimeRoot) { $RuntimeRoot = Join-Path $packageRoot 'runtime' }
    $runtime = (Resolve-Path -LiteralPath $RuntimeRoot).Path
    $pythonHome = Join-Path $runtime 'apps\Python312'
    $qgisRoot = Join-Path $runtime 'apps\qgis-ltr'
    foreach ($required in @('bin\python3.exe', 'apps\qgis-ltr\python\qgis\__init__.py', 'share\proj\proj.db')) {
        if (-not (Test-Path -LiteralPath (Join-Path $runtime $required))) { throw "Incomplete runtime: $required" }
    }
    $env:OSGEO4W_ROOT = $runtime
    $env:PATH = "$qgisRoot\bin;$runtime\apps\Qt5\bin;$runtime\bin;$env:WINDIR\System32;$env:WINDIR"
    $env:PYTHONHOME = $pythonHome
    $env:PYTHONPATH = "$qgisRoot\python;$packageRoot\src"
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONUTF8 = '1'
    $env:QGIS_PREFIX_PATH = $qgisRoot.Replace('\', '/')
    $env:QT_PLUGIN_PATH = "$qgisRoot\qtplugins;$runtime\apps\Qt5\plugins"
    $env:QT_QPA_PLATFORM_PLUGIN_PATH = "$runtime\apps\Qt5\plugins\platforms"
    $env:GDAL_DATA = "$runtime\apps\gdal\share\gdal"
    $env:GDAL_DRIVER_PATH = "$runtime\apps\gdal\lib\gdalplugins"
    $env:PROJ_DATA = "$runtime\share\proj"
    $env:PROJ_LIB = $env:PROJ_DATA
    $env:GDAL_FILENAME_IS_UTF8 = 'YES'
    $env:PROJ_NETWORK = 'OFF'
    # Avoid inheriting another Python/Qt application configuration.
    Remove-Item Env:QT_API, Env:PYTHONSTARTUP -ErrorAction SilentlyContinue
    $stateRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ETOPO2022Analyzer'
    if ($env:ETOPO_STATE_DIR) { $stateRoot = $env:ETOPO_STATE_DIR }
    if (-not $env:ETOPO_USER_DIR) { $env:ETOPO_USER_DIR = Join-Path $stateRoot 'outputs' }
    $logRoot = Join-Path $stateRoot 'logs'
    New-Item -ItemType Directory -Force -Path $logRoot, $env:ETOPO_USER_DIR | Out-Null
    $env:MPLCONFIGDIR = Join-Path $stateRoot 'matplotlib'
    $env:QGIS_CUSTOM_CONFIG_PATH = Join-Path $stateRoot 'qgis'
    if ($Mode -in @('Check', 'SmokeGui', 'BuildData')) {
        $env:QT_QPA_PLATFORM = 'offscreen'
        if (-not $Report) { $Report = Join-Path $logRoot 'self-check.json' }
        if ($Mode -eq 'Check') {
            New-Item -ItemType Directory -Force -Path (Split-Path ([IO.Path]::GetFullPath($Report)) -Parent) | Out-Null
            '{"passed":false,"stage":"starting"}' | Set-Content -LiteralPath $Report -Encoding UTF8
        }
        $arguments = @((Join-Path $packageRoot 'main.py'))
        if ($Mode -eq 'Check') { $arguments += @('--self-check', '--report', $Report) }
        elseif ($Mode -eq 'BuildData') { $arguments += '--create-demo' }
        else { $arguments += '--smoke-gui' }
        & (Join-Path $runtime 'bin\python3.exe') @arguments
        $processExitCode = $LASTEXITCODE
        if ($Mode -eq 'Check') {
            $checkResult = Get-Content -LiteralPath $Report -Raw -Encoding UTF8 | ConvertFrom-Json
            $checkResult | Add-Member -NotePropertyName process_exit_code -NotePropertyValue $processExitCode -Force
            if ($processExitCode -ne 0) { $checkResult.passed = $false }
            $checkResult | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Report -Encoding UTF8
        }
        exit $processExitCode
    }
    $env:QT_QPA_PLATFORM = 'windows'
    $arguments = '"' + (Join-Path $packageRoot 'main.py') + '"'
    if ($Mode -eq 'Demo') { $arguments += ' --demo' }
    if ($VerifyWindow) {
        if (-not $Report) { $Report = Join-Path $logRoot "visible-$Mode.json" }
        $arguments += ' --verify-window "' + $Report + '"'
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $errorLog = Join-Path $logRoot "startup-$stamp-error.log"
    # pythonw has no console. Its application window must be shown normally.
    $process = Start-Process -FilePath (Join-Path $pythonHome 'pythonw.exe') -ArgumentList $arguments -WorkingDirectory $packageRoot -WindowStyle Normal -PassThru -Wait -RedirectStandardOutput (Join-Path $logRoot "startup-$stamp.log") -RedirectStandardError $errorLog
    if ($process.ExitCode -ne 0) { throw "Application exited with code $($process.ExitCode). Log: $errorLog" }
} catch {
    Write-Error $_ -ErrorAction Continue
    if ($Mode -in @('Run', 'Demo')) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'ETOPO2022 Analyzer - startup failed') | Out-Null
    }
    exit 1
}
