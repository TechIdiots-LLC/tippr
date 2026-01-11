$commit = '90ff4b5aba44afdf871fa8f0b7b70f4c69d7060f'
$files = git diff --name-only "$commit..HEAD" | Where-Object { $_ -and (Test-Path $_) }
if (-not $files) {
    Write-Output 'No files changed since that commit or no valid paths to scan.'
    exit 0
}
$patterns = @(
    'Tippr Engineering',
    'TipprEng',
    'Tippr Lessons',
    'Tippr scaling',
    'Tippr talk',
    'tippr.net/r/RedditEng',
    'tippr.net/r/Reddit',
    'Tippr\s+Engineering',
    'Tippr\s+Lessons'
)
Select-String -Path $files -Pattern $patterns -SimpleMatch -ErrorAction SilentlyContinue | Select-Object Path,LineNumber,Line | Format-Table -AutoSize
