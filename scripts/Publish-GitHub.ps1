param(
    [string]$ReleaseDirectory = (Split-Path -Parent $PSScriptRoot | Split-Path -Parent)
)
$ErrorActionPreference = 'Stop'
$sourceDirectory = Split-Path -Parent $PSScriptRoot
$repository = 'shardulnarvekar/just-trim'
$remoteUrl = 'https://github.com/shardulnarvekar/just-trim.git'
$tag = 'v1.1.1'
$archive = Join-Path $ReleaseDirectory 'JustTrim-Windows.zip'
$checksum = Join-Path $ReleaseDirectory 'JustTrim-Windows.zip.sha256.txt'
$notes = Join-Path $sourceDirectory 'docs/RELEASE-NOTES.md'

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE. No force push or overwrite was attempted." }
}

Get-Command gh, git -ErrorAction Stop | Out-Null
foreach ($file in @($archive, $checksum, $notes)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing release file: $file" }
}
$expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0]
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'Archive checksum mismatch.' }
$account = & gh api user --jq .login
if ($LASTEXITCODE -ne 0 -or $account.Trim() -ne 'shardulnarvekar') {
    throw 'Run this script in your own PowerShell session with gh signed in as shardulnarvekar.'
}

Push-Location -LiteralPath $sourceDirectory
try {
    if (& git status --porcelain) { throw 'Source has uncommitted changes; review and commit them before publishing.' }
    Invoke-Checked -Program git -Arguments @('rev-parse', '--verify', $tag)
    $details = & gh repo view $repository --json nameWithOwner,isPrivate 2>$null
    if ($LASTEXITCODE -ne 0) {
        Invoke-Checked -Program gh -Arguments @('repo', 'create', $repository, '--private', '--description', 'Lossless Windows MOV clipper by Shardul Narvekar')
        $details = & gh repo view $repository --json nameWithOwner,isPrivate
        if ($LASTEXITCODE -ne 0) { throw 'Could not verify the created repository.' }
    }
    $repo = $details | ConvertFrom-Json
    if (-not $repo.isPrivate -or $repo.nameWithOwner -ne $repository) { throw 'Expected a private repository owned by shardulnarvekar.' }
    $origin = & git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) {
        Invoke-Checked -Program git -Arguments @('remote', 'add', 'origin', $remoteUrl)
    } elseif ($origin.Trim() -ne $remoteUrl) {
        throw "Existing origin points elsewhere: $origin"
    }
    # Use gh's authenticated helper for this push only; do not modify global Git settings.
    Invoke-Checked -Program git -Arguments @('-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', '-u', 'origin', 'main', $tag)
    & gh release view $tag --repo $repository *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Release already exists. Existing assets were not overwritten.'
    } else {
        Invoke-Checked -Program gh -Arguments @('release', 'create', $tag, $archive, $checksum, '--repo', $repository,
            '--verify-tag', '--title', 'Just Trim 1.1.1', '--notes-file', $notes)
    }
    Invoke-Checked -Program gh -Arguments @('repo', 'view', $repository, '--json', 'url,isPrivate')
    Invoke-Checked -Program gh -Arguments @('release', 'view', $tag, '--repo', $repository, '--json', 'url,assets')
} finally {
    Pop-Location
}
