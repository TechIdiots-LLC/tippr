# The contents of this file are subject to the Common Public Attribution
# License Version 1.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is Tippr.
#
# The Initial Developer of the Original Code is TechIdiots LLC.
# Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
###############################################################################

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
