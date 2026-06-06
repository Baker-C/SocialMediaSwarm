# Sync repo to origin/main and rebuild/restart the Docker Compose stack.
# Invoked by .github/workflows/deploy.yml on push to main (self-hosted runner).
param(
    [string]$RepoRoot = $env:SMA_REPO_ROOT,
    [string]$ExpectedSha = "",
    [switch]$SkipGitSync
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = "C:\Users\cdbak\_SocialMediaDomination"
}

$ComposeDir = Join-Path $RepoRoot "SocialMediaAutonomousAgents"
$LogDir = Join-Path $RepoRoot "SocialMediaAutonomousAgents\scripts\logs"
$StampFile = Join-Path $ComposeDir ".deploy-stamp"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$LogFile = Join-Path $LogDir ("deploy-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "o"), $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$MaxAttempts = 30,
        [int]$DelaySeconds = 2
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                Write-Log "Health check passed: $Url (attempt $attempt)"
                return
            }
        } catch {
            Write-Log "Health check waiting: $Url (attempt $attempt/$MaxAttempts)"
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Health check failed for $Url after $MaxAttempts attempts"
}

Write-Log "Deploy started (repo=$RepoRoot expected_sha=$ExpectedSha skip_git=$SkipGitSync)"

if (-not (Test-Path $ComposeDir)) {
    throw "Compose directory not found: $ComposeDir"
}

if (-not $SkipGitSync) {
    Write-Log "Fetching origin/main"
    git -C $RepoRoot fetch origin main

    $localSha = (git -C $RepoRoot rev-parse HEAD).Trim()
    $remoteSha = (git -C $RepoRoot rev-parse origin/main).Trim()

    if ($localSha -eq $remoteSha) {
        Write-Log "Already on origin/main ($localSha); rebuilding stack to pick up image/env changes"
    } else {
        Write-Log "Updating $localSha -> $remoteSha"
        git -C $RepoRoot reset --hard origin/main
    }
}

$currentSha = (git -C $RepoRoot rev-parse HEAD).Trim()
Write-Log "Active commit: $currentSha"

if ($ExpectedSha -and $currentSha -ne $ExpectedSha.Trim()) {
    throw "Commit mismatch after sync: expected $ExpectedSha got $currentSha"
}

if (-not (Test-Path (Join-Path $ComposeDir "backend\.env"))) {
    throw "Missing backend/.env — create it from backend/.env.example before deploying"
}

Set-Location $ComposeDir
Write-Log "Running docker compose up -d --build"
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed with exit code $LASTEXITCODE"
}

Wait-HttpOk -Url "http://localhost:8000/api/health"
Wait-HttpOk -Url "http://localhost:3000" -MaxAttempts 45 -DelaySeconds 3

$stamp = Get-Content -Path $StampFile -ErrorAction SilentlyContinue
Write-Log "Deploy complete (sha=$currentSha stamp=$stamp log=$LogFile)"
