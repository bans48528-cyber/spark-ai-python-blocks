param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseRoot = Join-Path $projectRoot "release"
$buildRoot = Join-Path $projectRoot "build"
$distRoot = Join-Path $projectRoot "dist"
$appName = "SparkAI-Generator"
$appDirectory = Join-Path $releaseRoot $appName

Set-Location $projectRoot

if (-not $SkipTests) {
    python -m unittest discover -s tools -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "Tests failed. Release was not built." }
}

python -m pip install --disable-pip-version-check pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed." }

foreach ($path in @($buildRoot, $distRoot, $releaseRoot)) {
    if (Test-Path $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}

python -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name $appName `
    --add-data "templates;templates" `
    --add-data "docs;docs" `
    SparkAI_Generator.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
Move-Item -LiteralPath (Join-Path $distRoot $appName) -Destination $releaseRoot
Copy-Item -LiteralPath (Join-Path $projectRoot ".env") -Destination (Join-Path $appDirectory ".env") -Force

@"
Spark AI Generator

1. Double-click SparkAI-Generator.exe.
2. The local web page opens automatically.
3. Generate and download .sparkai files from the page.

Python is bundled. Do not install Python or run pip.
The built-in default AI key is stored in .env. Keep this folder private.
Spark AI software is still required to open and run generated projects.
"@ | Set-Content -LiteralPath (Join-Path $appDirectory "README.txt") -Encoding ascii

Compress-Archive -LiteralPath $appDirectory -DestinationPath (Join-Path $releaseRoot "$appName.zip") -Force
Write-Host "Release created: $appDirectory"
Write-Host "Archive created: $(Join-Path $releaseRoot "$appName.zip")"
