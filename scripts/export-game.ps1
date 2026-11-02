$ErrorActionPreference = 'Stop'
$taskServer = Split-Path -Parent $PSScriptRoot
$taskProject = [System.IO.Path]::GetFullPath((Join-Path $taskServer '..\..\youbeatai-godot-web'))
$taskExport = Join-Path $taskServer '.godot-export'
$taskGodot = if ($env:GODOT_BIN) { $env:GODOT_BIN } else { 'D:\Godot 4.6\godot.exe' }
if (-not (Test-Path -LiteralPath $taskGodot)) { throw 'Stel GODOT_BIN in op de Godot 4.6 Standard executable.' }
New-Item -ItemType Directory -Path $taskExport -Force | Out-Null
$taskStage = Join-Path ([System.IO.Path]::GetTempPath()) ('ritmerobot-export-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskStage | Out-Null
$taskLogs = Join-Path $taskServer 'work'
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskStdout = Join-Path $taskLogs 'godot-export.out.log'
$taskStderr = Join-Path $taskLogs 'godot-export.err.log'
try {
    $taskArguments = '--headless --path "{0}" --export-release "Web" "{1}"' -f $taskProject, (Join-Path $taskStage 'ritme_robot.html')
    $taskProcess = Start-Process -FilePath $taskGodot -ArgumentList $taskArguments -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput $taskStdout -RedirectStandardError $taskStderr
    & node (Join-Path $PSScriptRoot 'validate-godot-export.mjs') "$($taskProcess.ExitCode)" $taskStdout $taskStderr $taskStage
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $taskStdout -Tail 20
        Get-Content -LiteralPath $taskStderr -Tail 40
        throw "Godot-export bevat fouten (exitcode $($taskProcess.ExitCode)). Zie work/godot-export.*.log."
    }
    Copy-Item -Path (Join-Path $taskStage '*') -Destination $taskExport -Recurse -Force
} finally {
    $taskTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $taskResolvedStage = [System.IO.Path]::GetFullPath($taskStage)
    if ((Split-Path -Parent $taskResolvedStage).TrimEnd('\') -ieq $taskTempRoot.TrimEnd('\') -and (Split-Path -Leaf $taskResolvedStage) -match '^ritmerobot-export-[a-f0-9]{32}$') {
        Remove-Item -LiteralPath $taskResolvedStage -Recurse -Force
    }
}
Write-Output "Godot 4.6 webexport gereed: $taskExport"
