param(
    [string]$PythonPath = '',
    [string]$ScannerWslPath = '',
    [string]$Distro = 'Ubuntu',
    [string]$DatabasePath = '',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$projectPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonCommand = ''
$pythonArguments = @()
$candidates = @()
if ($PythonPath) {
    $candidates += @{ Command = $PythonPath; Arguments = @() }
} else {
    foreach ($name in @('python', 'py')) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found) {
            $arguments = @()
            if ($name -eq 'py') { $arguments = @('-3') }
            $candidates += @{ Command = $found.Source; Arguments = $arguments }
        }
    }
}
foreach ($candidate in $candidates) {
    try {
        $probeArguments = @($candidate.Arguments) + @('-c', 'import os,sys; assert os.name == "nt" and sys.version_info >= (3,10); print(sys.executable)')
        $probe = & $candidate.Command @probeArguments 2>$null
        if ($LASTEXITCODE -eq 0 -and $probe) {
            $pythonCommand = $candidate.Command
            $pythonArguments = @($candidate.Arguments)
            break
        }
    } catch { continue }
}
if (-not $pythonCommand) {
    throw 'Windows Python 3.10+ was not found. Run again with -PythonPath followed by the full python.exe path.'
}
$env:CORESPACE_WSL_DISTRO = $Distro
if ($ScannerWslPath) { $env:CORESPACE_SCANNER_WSL_PATH = $ScannerWslPath }
if ($DatabasePath) { $env:CORESPACE_DB_PATH = [System.IO.Path]::GetFullPath($DatabasePath) }
Write-Host "Python: $probe"
Write-Host "WSL distro: $Distro"
if ($env:CORESPACE_SCANNER_WSL_PATH) {
    $wslCommand = 'wsl.exe'
    if ($env:CORESPACE_WSL) { $wslCommand = $env:CORESPACE_WSL }
    & $wslCommand -d $Distro --exec test -x $env:CORESPACE_SCANNER_WSL_PATH
    if ($LASTEXITCODE -ne 0) { throw 'The scanner is unavailable or not executable in the selected WSL distro.' }
    Write-Host "Scanner: $env:CORESPACE_SCANNER_WSL_PATH"
} else {
    Write-Host 'C scanner is not configured. The prototype and explicitly selected sample API can still be tested.'
}
if ($CheckOnly) { return }
Push-Location $projectPath
try {
    $runArguments = @($pythonArguments) + @(Join-Path $projectPath 'main.py')
    & $pythonCommand @runArguments
    exit $LASTEXITCODE
} finally { Pop-Location }
