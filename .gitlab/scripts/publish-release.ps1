# Creates the GitLab release for the files release-build.sh uploaded to the generic package registry (listed in
# release-files.txt), with CHANGELOG.md's section for the version and the download notes of the GitHub release as
# its description. Files are linked permanently as <project>/-/releases/<tag>/downloads/<file>.

$ErrorActionPreference = 'Stop'

if ($env:RELEASE_PUBLISH -ne 'true') {
    Write-Host "Not publishing $env:RELEASE_TAG (dry run, or already released)."
    exit 0
}

$version = $env:RELEASE_VERSION
$tag = $env:RELEASE_TAG
$api = "$env:CI_API_V4_URL/projects/$env:CI_PROJECT_ID"
$jobHeaders = @{ 'JOB-TOKEN' = $env:CI_JOB_TOKEN }

$files = @(Get-Content release-files.txt | Where-Object { $_.Trim() })
if (-not $files) { throw 'release-files.txt lists no files' }

# The lines under "## <version>" up to the next "## " heading
$notes = @()
$inSection = $false
foreach ($line in Get-Content CHANGELOG.md -Encoding UTF8) {
    if ($line -eq "## $version") { $inSection = $true; continue }
    if ($inSection -and $line -match '^## ') { break }
    if ($inSection) { $notes += $line }
}
$image = if ($env:DOCKERHUB_IMAGE) { $env:DOCKERHUB_IMAGE } else { 'techidiotsllc/tippr' }
$notes += @(
    ''
    '## Downloads'
    ''
    "- **Docker:** ``docker pull ${image}:$version``, or unpack ``tippr-$version-compose.tar.gz``, copy"
    '  `.env.example` to `.env`, fill it in and run `docker compose up -d` (docker/README.md).'
    "- **Proxmox:** ``tippr-$version-proxmox-amd64.tar.zst`` is an LXC template with the whole site installed;"
    "  create a container with the site's domain as its hostname and start it (docs/PROXMOX.md)."
    "- **Installer (Ubuntu 24.04):** unpack ``tippr-$version-installer.tar.gz`` into ``/home/tippr/src`` and"
    '  run `sudo TIPPR_USER=tippr TIPPR_DOMAIN=example.com ./install-tippr.sh` in `tippr/`; it doesn''t need'
    '  to clone anything (docs/INSTALL_tippr.md).'
    ''
    '`SHA256SUMS` lists the files'' checksums.'
)
$description = ($notes -join "`n").Trim()
Write-Host "--- Release notes ---`n$description"

$links = @()
foreach ($name in $files) {
    $url = "$api/packages/generic/tippr/$version/$([uri]::EscapeDataString($name))"
    $links += @{ name = $name; url = $url; direct_asset_path = "/$name"; link_type = 'package' }
}

$release = @{
    name        = if ($env:RELEASE_PRERELEASE -eq 'true') { "tippr $tag (pre-release)" } else { "tippr $tag" }
    tag_name    = $tag
    ref         = $env:CI_COMMIT_SHA
    description = $description
    assets      = @{ links = $links }
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri "$api/releases" -Headers $jobHeaders -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($release)) | Out-Null
Write-Host "Created release ${tag}: $env:CI_PROJECT_URL/-/releases/$([uri]::EscapeDataString($tag))"
