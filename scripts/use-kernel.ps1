<#
    Point FL Studio's MIDI input device at a controller script, by registry.

    FL binds an input device to a script folder and only reads that binding at
    startup, so this must run with FL CLOSED. FL rewrites its own registry
    config on exit, which means an edit made while FL is running is discarded
    without any error and looks exactly like a script that failed to load.

    Nothing here overwrites an existing script. Switching back is one command,
    which is the point: the old bridge stays intact and usable.

        .\use-kernel.ps1                    show what is bound now
        .\use-kernel.ps1 -Use AgentFL       bind the kernel
        .\use-kernel.ps1 -Use FLStudioMCP   put the old bridge back
#>
[CmdletBinding()]
param(
    [string] $Use,
    [string] $Device = 'FLStudioMCP RX',
    [string] $FLVersionKey = 'FL Studio 24'
)

$ErrorActionPreference = 'Stop'

$devicePath = "HKCU:\Software\Image-Line\$FLVersionKey\Devices\MIDI input\$Device"
if (-not (Test-Path $devicePath)) {
    throw "No registry entry for input device '$Device' under '$FLVersionKey'. FL has to have seen the port at least once."
}

function Show-Binding {
    $p = Get-ItemProperty $devicePath
    [PSCustomObject]@{
        Device       = $Device
        ScriptFolder = $p.ScriptFolder
        Port         = $p.Port
        Enabled      = $p.Enabled
    } | Format-List

    $outPath = "HKCU:\Software\Image-Line\$FLVersionKey\Devices\MIDI output"
    Get-ChildItem $outPath -ErrorAction SilentlyContinue | ForEach-Object {
        $n = Split-Path $_.Name -Leaf
        $port = (Get-ItemProperty $_.PSPath).Port
        "  output '$n' port=$port"
    }
    ""
    "The script's replies go to whichever OUTPUT device carries the SAME port"
    "number as the input above. That pairing is the routing."
}

if (-not $Use) {
    Show-Binding
    return
}

$fl = Get-Process -Name 'FL64', 'FL' -ErrorAction SilentlyContinue
if ($fl) {
    Write-Host "FL Studio is running (PID $($fl.Id -join ', '))." -ForegroundColor Yellow
    Write-Host "It rewrites this key on exit, so an edit now would be silently discarded."
    Write-Host "Close FL first, then run this again."
    return
}

$scriptDir = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings\Hardware\$Use"
if (-not (Test-Path $scriptDir)) {
    throw "No controller script folder at $scriptDir. Run kernel\install.ps1 first."
}

$previous = (Get-ItemProperty $devicePath).ScriptFolder
Set-ItemProperty $devicePath -Name 'ScriptFolder' -Value $Use
Set-ItemProperty $devicePath -Name 'Enabled' -Value 1 -Type DWord

Write-Host "Bound '$Device' to script '$Use' (was '$previous')." -ForegroundColor Green
Write-Host "Start FL Studio. Revert any time with:  .\use-kernel.ps1 -Use $previous"
