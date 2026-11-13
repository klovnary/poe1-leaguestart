# Builds dist\League-Start-Tracker-Setup.exe on Windows. GitHub Actions runs this
# for every release; you can also run it yourself with Python 3.13 and Inno Setup 6:
#   pwsh installer/build.ps1 -Version 0.2.0
param(
    [string]$Version = "0.1.0",
    [string]$Commit = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$build = Join-Path $root "build"
$dist = Join-Path $root "dist"
Remove-Item $build, $dist -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$build\python", "$build\app", $dist | Out-Null

# 1. A private copy of Python: the official "embeddable" build of the same version
$pyver = (python -c "import sys; print('%d.%d.%d' % sys.version_info[:3])").Trim()
$tag = (python -c "import sys; print('%d%d' % sys.version_info[:2])").Trim()
$pyhome = (python -c "import sys; print(sys.base_prefix)").Trim()
Write-Host "Python $pyver from $pyhome"
$tmp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$zip = Join-Path $tmp "python-embed.zip"
Invoke-WebRequest "https://www.python.org/ftp/python/$pyver/python-$pyver-embed-amd64.zip" -OutFile $zip
Expand-Archive $zip "$build\python" -Force
Set-Content "$build\python\python$tag._pth" -Encoding ascii -Value @(
    "python$tag.zip", ".", "Lib", "..\app", "import site")

# 2. tkinter (the window). The embeddable Python leaves it out, so copy it from
#    the full Python that's running this script.
Copy-Item "$pyhome\Lib\tkinter" "$build\python\Lib\tkinter" -Recurse
Copy-Item "$pyhome\DLLs\_tkinter.pyd" "$build\python\"
Get-ChildItem "$pyhome\DLLs" -Filter "*.dll" | Where-Object { $_.Name -match '^(tcl|tk|zlib)' } |
    Copy-Item -Destination "$build\python\"
Copy-Item "$pyhome\tcl" "$build\python\tcl" -Recurse
Get-ChildItem "$build\python\Lib" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# 3. The tracker itself
Get-ChildItem $root -Filter "*.py" | Copy-Item -Destination "$build\app\"
if (-not $Commit) { $Commit = (git -C $root rev-parse HEAD).Trim() }
@{ commit = $Commit; installer = $Version } | ConvertTo-Json | Set-Content "$build\app\version.json" -Encoding utf8

# 4. The launcher (League Start Tracker.exe), compiled with the C# compiler that ships with Windows
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
& $csc /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll `
    "/out:$build\League Start Tracker.exe" (Join-Path $PSScriptRoot "launcher.cs")
if ($LASTEXITCODE) { throw "launcher build failed" }

# 5. Check the bundled Python can load the tracker and tkinter
Push-Location "$build\app"
& "$build\python\python.exe" -c "import tkinter, tracker, updater; tkinter.Tcl(); print('bundle ok')"
$ok = $LASTEXITCODE
Pop-Location
if ($ok) { throw "bundle check failed" }

# 6. The installer
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "$env:ProgramFiles\Inno Setup 6\ISCC.exe" }
& $iscc "/DAppVersion=$Version" (Join-Path $PSScriptRoot "LeagueStartTracker.iss")
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-ChildItem $dist
