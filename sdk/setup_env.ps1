<#
.SYNOPSIS
Set up the offline SDK research environment on a new Windows machine.

.DESCRIPTION
Creates a virtual environment in .agents/sdk-venv (ignored by Git), installs
the pinned research dependencies and runs `check-env`, which lists the game
files, research caches and optional Ghidra settings that are still missing.
Run it from any directory:

    powershell -ExecutionPolicy Bypass -File sdk/enemy_logic_exporter/setup_env.ps1

Afterwards run SDK commands from the repository root with
.agents/sdk-venv/Scripts/python.exe -m sdk.enemy_logic_exporter <command>.
#>
param(
    # Python launcher version; 3.13 is the verified one.
    [string]$PythonVersion = "3.13",
    # Game executable when it is not in a Steam library (sets MHWS_EXE for this session).
    [string]$Exe = ""
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$venv = Join-Path $root ".agents/sdk-venv"
$python = Join-Path $venv "Scripts/python.exe"

if (-not (Test-Path $python)) {
    New-Item -ItemType Directory -Force (Join-Path $root ".agents") | Out-Null
    & py "-$PythonVersion" -m venv $venv
    if ($LASTEXITCODE) { throw "py -$PythonVersion 不可用；先安装 Python $PythonVersion（含 py 启动器）" }
}
& $python -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE) { throw "依赖安装失败" }
if ($Exe) { $env:MHWS_EXE = $Exe }

Push-Location $root
try {
    & $python -B -m sdk.enemy_logic_exporter check-env
    if ($LASTEXITCODE) {
        Write-Host "仍有缺失项（见上方 missing）。补齐后重新运行 check-env。" -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}
