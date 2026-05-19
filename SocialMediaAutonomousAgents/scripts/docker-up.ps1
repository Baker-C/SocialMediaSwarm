# Build and start app stack (RavenDB must already be running).
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Ensure RavenDB is up: docker compose -f $env:USERPROFILE\ravendb\docker-compose.yml up -d"
docker compose up -d --build
docker compose ps
