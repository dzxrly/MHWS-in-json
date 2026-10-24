<#
.SYNOPSIS
Set up the offline SDK research environment on a new Windows machine.

.DESCRIPTION
Creates a virtual environment in .agents/sdk-venv (ignored by Git), installs
the pinned research dependencies and runs `check-env`, which lists the game
files, research caches and optional Ghidra settings that are still missing.
Run it from any directory:

    powershell -ExecutionPolicy Bypass -File sdk/setup_env.ps1

Afterwards run .agents/sdk-venv/Scripts/python.exe -m sdk (menu), or
-m sdk.<tool> <command>. The script registers the repository root in the
environment (mhws_sdk.pth), so the sdk package is found from any directory.
#>
param(
    # Python launcher version; 3.13 is the verified one.
    [string]$PythonVersion = "3.13",
    # Dumped game EXE checked by check-env (sets MHWS_EXE for this session).
    [string]$Exe = "",
    # REFramework il2cpp_dump.json checked by check-env (sets MHWS_IL2CPP for this session).
    [string]$Il2cpp = ""
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $root ".agents/sdk-venv"
$python = Join-Path $venv "Scripts/python.exe"

if (-not (Test-Path $python)) {
    New-Item -ItemType Directory -Force (Join-Path $root ".agents") | Out-Null
    & py "-$PythonVersion" -m venv $venv
    if ($LASTEXITCODE) { throw "py -$PythonVersion 不可用；先安装 Python $PythonVersion（含 py 启动器）" }
}
& $python -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE) { throw "依赖安装失败" }
# Put the repository root on sys.path so `python -m sdk` works outside the root.
$sitePackages = Join-Path $venv "Lib/site-packages"
[IO.File]::WriteAllText((Join-Path $sitePackages "mhws_sdk.pth"), $root)
if ($Exe) { $env:MHWS_EXE = $Exe }
if ($Il2cpp) { $env:MHWS_IL2CPP = $Il2cpp }

Push-Location $root
try {
    & $python -B -m sdk.enemy_logic_exporter check-env
    if ($LASTEXITCODE) {
        Write-Host "仍有缺失项（见上方 missing）。补齐后重新运行 check-env。" -ForegroundColor Yellow
    }
    Write-Host "菜单界面（任意目录均可运行）：& `"$python`" -m sdk"
}
finally {
    Pop-Location
}
