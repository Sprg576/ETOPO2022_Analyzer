param([string]$Pattern = 'test_*.py')

# 使用 QGIS 同目录解释器和 DLL，避免其他 Python/Qt 抢先加载依赖。
$ErrorActionPreference = 'Stop'
Get-Content 'D:\QGIS\bin\qgis-ltr-bin.env' | ForEach-Object {
    $entry = $_ -split '=', 2
    if ($entry.Length -eq 2) {
        [Environment]::SetEnvironmentVariable($entry[0], $entry[1], 'Process')
    }
}
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONPATH = 'D:\QGIS\apps\qgis-ltr\python'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & 'D:\QGIS\bin\python3.exe' -c "import os,sys; dlls=[os.add_dll_directory(p) for p in [r'D:\QGIS\bin',r'D:\QGIS\apps\Qt5\bin',r'D:\QGIS\apps\qgis-ltr\bin']]; from qgis.core import QgsApplication; import unittest; result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests',pattern=sys.argv[1])); sys.exit(not result.wasSuccessful())" $Pattern
    $testExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $testExitCode
