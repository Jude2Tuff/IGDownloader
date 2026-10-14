# Creates (or replaces) a Windows scheduled task that runs auto_download.py
# runs_per_day times a day, spread evenly, each with up to 1 hour of random delay.
# Run again after changing runs_per_day in config.json.
# Remove with: Unregister-ScheduledTask -TaskName IGDownloader -Confirm:$false

$root = $PSScriptRoot
$config = Get-Content (Join-Path $root "config.json") -Raw | ConvertFrom-Json
$runs = [int]$config.runs_per_day
$python = Join-Path $root ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $python)) { throw "Virtual environment not found. Run setup from the README first." }

$action = New-ScheduledTaskAction -Execute $python -Argument "auto_download.py" -WorkingDirectory $root

$triggers = @()
$spacing = 24 / $runs
for ($i = 0; $i -lt $runs; $i++) {
    $time = (Get-Date).Date.AddHours(8 + $i * $spacing)
    $triggers += New-ScheduledTaskTrigger -Daily -At $time -RandomDelay (New-TimeSpan -Hours 1)
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName "IGDownloader" -Action $action -Trigger $triggers -Settings $settings -Force | Out-Null

Write-Host "Scheduled IGDownloader to run $runs times a day at:"
$triggers | ForEach-Object { Write-Host ("  " + ([datetime]$_.StartBoundary).ToString("h:mm tt") + " (+ up to 1 hr random)") }
