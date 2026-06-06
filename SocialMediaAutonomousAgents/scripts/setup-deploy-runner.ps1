# One-time setup: download, register, and install a self-hosted GitHub Actions runner.
# Requires: gh CLI authenticated, Docker Desktop running as the same Windows user.
param(
    [string]$RepoRoot = "C:\Users\cdbak\_SocialMediaDomination",
    [string]$RunnerDir = "C:\Users\cdbak\actions-runner-sma",
    [string]$RunnerName = "sma-windows-deploy",
    [string]$RunnerLabel = "sma-deploy",
    [string]$RepoSlug = "Baker-C/SocialMediaSwarm"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required"
}

if (-not (Test-Path $RunnerDir)) {
    New-Item -ItemType Directory -Path $RunnerDir -Force | Out-Null
}

Set-Location $RunnerDir

$version = "2.327.1"
$zipName = "actions-runner-win-x64-$version.zip"
$zipPath = Join-Path $RunnerDir $zipName

if (-not (Test-Path ".\config.cmd")) {
    Write-Host "Downloading actions-runner $version"
    Invoke-WebRequest `
        -Uri "https://github.com/actions/runner/releases/download/v$version/$zipName" `
        -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $RunnerDir -Force
}

$token = gh api -X POST "repos/$RepoSlug/actions/runners/registration-token" --jq .token
if (-not $token) {
    throw "Failed to obtain runner registration token"
}

Write-Host "Configuring runner $RunnerName with label $RunnerLabel"
.\config.cmd `
    --url "https://github.com/$RepoSlug" `
    --token $token `
    --name $RunnerName `
    --labels $RunnerLabel `
    --unattended `
    --replace

[Environment]::SetEnvironmentVariable("SMA_REPO_ROOT", $RepoRoot, "User")
Write-Host "Set user env SMA_REPO_ROOT=$RepoRoot"

Write-Host "Registering logon scheduled task for runner auto-start"
$runCmd = Join-Path $RunnerDir "run.cmd"
$action = New-ScheduledTaskAction -Execute $runCmd -WorkingDirectory $RunnerDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask `
    -TaskName "SMA-GitHub-Actions-Runner" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Self-hosted runner for SocialMediaSwarm push deploy" `
    -Force | Out-Null

Write-Host "Starting runner process (must run as the Docker Desktop user)"
$runnerProcess = Start-Process -FilePath $runCmd -WorkingDirectory $RunnerDir -WindowStyle Hidden -PassThru
Write-Host "Runner PID $($runnerProcess.Id)"

Write-Host "Runner installed. Verify with: gh api repos/$RepoSlug/actions/runners"
