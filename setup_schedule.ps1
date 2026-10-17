# Creates (or replaces) a Windows scheduled task that runs auto_download.py
# runs_per_day times a day, spread evenly starting at midnight (2 = 12 AM and 12 PM).
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
    $time = (Get-Date).Date.AddHours($i * $spacing)
    $triggers += New-ScheduledTaskTrigger -Daily -At $time
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName "IGDownloader" -Action $action -Trigger $triggers -Settings $settings -Force | Out-Null

Write-Host "Scheduled IGDownloader to run $runs times a day at:"
$triggers | ForEach-Object { Write-Host ("  " + ([datetime]$_.StartBoundary).ToString("h:mm tt")) }

# Posting: 2 reels and 2 images/slideshows a day (upload.py).
# Remove with: Unregister-ScheduledTask -TaskName IGUpload-Reels,IGUpload-Posts -Confirm:$false
foreach ($job in @(@{Name = "IGUpload-Reels"; Kind = "reel"; At = @("9:00", "17:00")},
                   @{Name = "IGUpload-Posts"; Kind = "post"; At = @("13:00", "21:00")})) {
    $uploadAction = New-ScheduledTaskAction -Execute $python -Argument "upload.py $($job.Kind)" -WorkingDirectory $root
    $uploadTriggers = $job.At | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
    Register-ScheduledTask -TaskName $job.Name -Action $uploadAction -Trigger $uploadTriggers -Settings $settings -Force | Out-Null
    Write-Host "Scheduled $($job.Name) at $($job.At -join ' and ')"
}
