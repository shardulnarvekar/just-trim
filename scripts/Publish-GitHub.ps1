param([string]$Tag = 'v1.1.2')
$ErrorActionPreference = 'Stop'
$sourceDirectory = Split-Path -Parent $PSScriptRoot
$repository = 'shardulnarvekar/just-trim'
$remoteUrl = 'https://github.com/shardulnarvekar/just-trim.git'
$notes = Join-Path $sourceDirectory 'docs/RELEASE-NOTES.md'

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE." }
}

Get-Command gh, git -ErrorAction Stop | Out-Null
$account = & gh api user --jq .login
if ($LASTEXITCODE -ne 0 -or $account.Trim() -ne 'shardulnarvekar') {
    throw 'Sign in to gh as shardulnarvekar in your own PowerShell session first.'
}
Push-Location -LiteralPath $sourceDirectory
try {
    if (& git status --porcelain) { throw 'Review and commit source changes before publishing.' }
    Invoke-Checked -Program git -Arguments @('rev-parse', '--verify', $Tag)
    $origin = & git remote get-url origin
    if ($LASTEXITCODE -ne 0 -or $origin.Trim() -ne $remoteUrl) { throw 'Unexpected Git origin.' }
    $details = & gh repo view $repository --json nameWithOwner,isPrivate
    if ($LASTEXITCODE -ne 0) { throw 'Could not read repository.' }
    $repo = $details | ConvertFrom-Json
    if ($repo.nameWithOwner -ne $repository) { throw 'Unexpected repository owner.' }
    Invoke-Checked -Program git -Arguments @('-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', '-u', 'origin', 'main', $Tag)
    & gh release view $Tag --repo $repository *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Release already exists; nothing was overwritten.'
    } else {
        # Source release only: never upload a bundled runtime before its
        # separate dependency-source/notice requirements are fulfilled.
        Invoke-Checked -Program gh -Arguments @('release', 'create', $Tag, '--repo', $repository,
            '--verify-tag', '--title', "Just Trim $Tag - source release", '--notes-file', $notes)
    }
    Invoke-Checked -Program gh -Arguments @('repo', 'view', $repository, '--json', 'url,isPrivate')
    Invoke-Checked -Program gh -Arguments @('release', 'view', $Tag, '--repo', $repository, '--json', 'url,assets')
} finally {
    Pop-Location
}
