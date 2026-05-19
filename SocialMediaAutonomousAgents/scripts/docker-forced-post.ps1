# Force a post via the Docker backend (do not run create_forced_post.py on the host).
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]]$AccountIds
)

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$args = @("compose", "exec", "-T", "backend", "python", "scripts/create_forced_post.py", "--force-now")
$args += $AccountIds

& docker @args
