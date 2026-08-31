<#
    Install the AgentFL kernel into FL Studio.

    You run this once. After that the kernel stays put and every new
    capability arrives as injected code, so there is no reason to run it
    again unless the protocol itself changes.

    FL only scans its Hardware folder at startup, so the one restart this
    triggers is also the last one you should ever need.
#>
[CmdletBinding()]
param(
    [string] $FLUserDir = "$env:USERPROFILE\Documents\Image-Line\FL Studio",
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

$source = Join-Path $PSScriptRoot 'device_AgentFL.py'
if (-not (Test-Path $source)) {
    throw "kernel source not found at $source"
}

$hardware = Join-Path $FLUserDir 'Settings\Hardware'
if (-not (Test-Path $hardware)) {
    throw @"
FL Studio's Hardware folder was not found at:
  $hardware
Pass -FLUserDir pointing at your FL Studio user folder (the one containing
Settings\Hardware).
"@
}

$target = Join-Path $hardware 'AgentFL'
$targetFile = Join-Path $target 'device_AgentFL.py'

if ((Test-Path $targetFile) -and -not $Force) {
    $existing = (Get-FileHash $targetFile -Algorithm SHA256).Hash
    $incoming = (Get-FileHash $source     -Algorithm SHA256).Hash
    if ($existing -eq $incoming) {
        Write-Host "Kernel already installed and identical. Nothing to do." -ForegroundColor Green
        Write-Host "  $targetFile"
        return
    }
    Write-Host "A different kernel is already installed. Re-run with -Force to replace it." -ForegroundColor Yellow
    Write-Host "  $targetFile"
    return
}

New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item $source $targetFile -Force

# A stale .pyc will be used in preference to the file you just wrote, which
# presents as an install that silently had no effect.
$pycache = Join-Path $target '__pycache__'
if (Test-Path $pycache) {
    Remove-Item $pycache -Recurse -Force
    Write-Host "Cleared stale __pycache__." -ForegroundColor DarkGray
}

Write-Host "Kernel installed." -ForegroundColor Green
Write-Host "  $targetFile"
Write-Host ""
Write-Host "Now, in FL Studio (Options > MIDI Settings):" -ForegroundColor Cyan
Write-Host "  INPUT list   enable 'FLStudioMCP RX', Controller type = AgentFL, Port = 42"
Write-Host "  OUTPUT list  enable 'FLStudioMCP TX', Port = 42   <- the same number"
Write-Host ""
Write-Host "The output half is the one everybody forgets. Without it the kernel"
Write-Host "runs perfectly and no reply ever reaches the agent."
Write-Host ""
Write-Host "Then restart FL once, and verify with:  python -m agentfl.doctor"
