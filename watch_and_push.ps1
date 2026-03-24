param(
    [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"

if ($IntervalMinutes -lt 1) {
    throw "IntervalMinutes must be 1 or more."
}

$scriptPath = Join-Path $PSScriptRoot "auto_push.ps1"
if (-not (Test-Path $scriptPath)) {
    throw "Missing auto_push.ps1 in project root."
}

Write-Host "Auto-push watcher started. Interval: $IntervalMinutes minute(s)."
Write-Host "Press Ctrl+C to stop."

while ($true) {
    & $scriptPath -Message "auto sync $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -SkipPull
    Start-Sleep -Seconds ($IntervalMinutes * 60)
}
