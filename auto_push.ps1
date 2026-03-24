param(
    [string]$Message = "",
    [switch]$SkipPull
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' is not installed or not in PATH."
    }
}

try {
    Require-Command "git"

    $isRepo = git rev-parse --is-inside-work-tree 2>$null
    if ($LASTEXITCODE -ne 0 -or $isRepo -ne "true") {
        throw "This folder is not a git repository. Run 'git init' first."
    }

    $remoteUrl = git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remoteUrl)) {
        throw "Remote 'origin' is missing. Add it with: git remote add origin <repo-url>"
    }

    if (-not $SkipPull) {
        git pull --rebase
    }

    git add -A

    $hasChanges = git diff --cached --name-only
    if ([string]::IsNullOrWhiteSpace($hasChanges)) {
        Write-Host "No changes to commit."
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($Message)) {
        $Message = "auto update $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    }

    git commit -m $Message
    git push

    Write-Host "Done. Changes were pushed to GitHub."
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
