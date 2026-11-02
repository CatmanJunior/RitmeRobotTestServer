param([switch] $SkipBuild)
$ErrorActionPreference = 'Stop'
$taskServer = Split-Path -Parent $PSScriptRoot
$taskFrontend = [System.IO.Path]::GetFullPath((Join-Path $taskServer '../ritmerobot-frontend'))
$taskBackend = [System.IO.Path]::GetFullPath((Join-Path $taskServer '../../backend/ritmerobot-backend'))
$taskTemplate = Join-Path $taskServer 'deployment'
$taskDist = Join-Path $taskServer 'dist'
if (-not $SkipBuild) {
	$taskPreviousExport = [Environment]::GetEnvironmentVariable('GODOT_EXPORT_DIR', 'Process')
	$taskPreviousDist = [Environment]::GetEnvironmentVariable('FRONTEND_DIST_DIR', 'Process')
	if (-not $taskPreviousExport) { $env:GODOT_EXPORT_DIR = Join-Path $taskServer '.godot-export' }
	$env:FRONTEND_DIST_DIR = $taskDist
	$taskPushed = $false
	try {
		Push-Location $taskFrontend
		$taskPushed = $true
		& npm run build
		if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
	} finally {
		if ($taskPushed) { Pop-Location }
		[Environment]::SetEnvironmentVariable('GODOT_EXPORT_DIR', $taskPreviousExport, 'Process')
		[Environment]::SetEnvironmentVariable('FRONTEND_DIST_DIR', $taskPreviousDist, 'Process')
	}
}
$taskRelease = (Get-Content -LiteralPath (Join-Path $taskDist 'play/build-version.txt') -Raw).Trim()
if ($taskRelease -notmatch '^[a-f0-9]{20}$') { throw 'No validated game build was found.' }
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$taskWork = Join-Path $taskServer 'work'
New-Item -ItemType Directory -Path $taskWork -Force | Out-Null
$taskBundle = Join-Path $taskWork "vps-test-$taskStamp"
if (Test-Path -LiteralPath $taskBundle) { throw "Bundle already exists: $taskBundle" }
New-Item -ItemType Directory -Path $taskBundle | Out-Null
$taskTemplateFiles = @(
	'README.md', '.env.example', 'backend.dockerignore', 'compose.yaml',
	'frontend/Dockerfile', 'frontend/nginx.conf', 'traefik/routes.yml.template',
	'scripts/configure-traefik.sh', 'scripts/generate-secrets.sh'
)
foreach ($taskRelative in $taskTemplateFiles) {
	$taskSource = Join-Path $taskTemplate $taskRelative
	$taskTarget = Join-Path $taskBundle $taskRelative
	New-Item -ItemType Directory -Path (Split-Path -Parent $taskTarget) -Force | Out-Null
	Copy-Item -LiteralPath $taskSource -Destination $taskTarget
}
$taskPublished = Join-Path $taskBundle 'frontend/dist'
New-Item -ItemType Directory -Path $taskPublished -Force | Out-Null
foreach ($taskName in @('index.html', 'manifest.webmanifest', 'service-worker.js', 'legacy-service-worker.js')) {
	Copy-Item -LiteralPath (Join-Path $taskDist $taskName) -Destination $taskPublished
}
Copy-Item -LiteralPath (Join-Path $taskDist 'admin') -Destination $taskPublished -Recurse
Copy-Item -LiteralPath (Join-Path $taskDist 'play') -Destination $taskPublished -Recurse

# Copy tracked backend source only; never copy its local environment, database, or keys.
$taskBackendTarget = Join-Path $taskBundle 'backend'
New-Item -ItemType Directory -Path $taskBackendTarget | Out-Null
$taskBackendFiles = & git -C $taskBackend -c core.quotepath=false ls-files
if ($LASTEXITCODE -ne 0) { throw 'Could not list backend source files.' }
foreach ($taskRelative in $taskBackendFiles) {
	if ($taskRelative -match '(^|/)(\.env[^/]*|\.git|data|\.venv|__pycache__)(/|$)' -or
		$taskRelative -match '\.(pem|key|pfx|p12|sqlite3|db|pyc)$') { continue }
	$taskSource = Join-Path $taskBackend $taskRelative
	if (-not (Test-Path -LiteralPath $taskSource -PathType Leaf)) { throw "Backend source is missing: $taskRelative" }
	$taskTarget = Join-Path $taskBackendTarget $taskRelative
	New-Item -ItemType Directory -Path (Split-Path -Parent $taskTarget) -Force | Out-Null
	Copy-Item -LiteralPath $taskSource -Destination $taskTarget
}
Copy-Item -LiteralPath (Join-Path $taskBundle 'backend.dockerignore') -Destination (Join-Path $taskBackendTarget '.dockerignore')

# Linux setup files must use LF even when Git checks them out with CRLF on Windows.
$taskTextPaths = @((Join-Path $taskBundle 'compose.yaml'), (Join-Path $taskBundle '.env.example'),
	(Join-Path $taskBundle 'frontend/Dockerfile'), (Join-Path $taskBundle 'frontend/nginx.conf'),
	(Join-Path $taskBundle 'traefik/routes.yml.template')) +
	@(Get-ChildItem -LiteralPath (Join-Path $taskBundle 'scripts') -Filter '*.sh' | Select-Object -ExpandProperty FullName)
foreach ($taskTextPath in $taskTextPaths) {
	$taskText = [System.IO.File]::ReadAllText($taskTextPath).Replace("`r`n", "`n")
	[System.IO.File]::WriteAllText($taskTextPath, $taskText)
}
$taskArchive = Join-Path $taskWork "ritmerobot-vps-test-$taskStamp.tar.gz"
& tar.exe -czf $taskArchive -C $taskBundle .
if ($LASTEXITCODE -ne 0) { throw 'Could not package the VPS test archive.' }
Write-Output "Bundle directory: $taskBundle"
Write-Output "Upload this archive: $taskArchive"
Write-Output "Included release: $taskRelease. No local database, secrets, or certificates were copied."
