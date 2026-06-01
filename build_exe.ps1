# LocalSTT Light Folder Distribution Builder

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "LocalSTT Light Folder Distribution Builder" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

Set-Location $PSScriptRoot

$pythonExe = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path (Resolve-Path "$PSScriptRoot\..") "venv\Scripts\python.exe"
}
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

& $pythonExe -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    & $pythonExe -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install PyInstaller" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

if (Test-Path "build") {
    Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue
}
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue
}
Get-Item "*.spec" -ErrorAction SilentlyContinue | Remove-Item -Force

$currentDir = Get-Location
$modelName = "faster-whisper-tiny.en"
$modelDataArgs = @()
$localModelsDir = Join-Path $currentDir "models"
if (Test-Path $localModelsDir) {
    Write-Host "Bundling LocalSTT_light models folder into distribution: $localModelsDir" -ForegroundColor Cyan
    $modelDataArgs = @("--add-data", "$localModelsDir;models")
} else {
    foreach ($candidate in @(
        (Join-Path (Resolve-Path "$currentDir\..") "models\$modelName"),
        "C:\Tools\models\$modelName"
    )) {
        if (Test-Path $candidate) {
            Write-Host "Bundling model folder into distribution: $candidate" -ForegroundColor Cyan
            $modelDataArgs = @("--add-data", "$candidate;models\$modelName")
            break
        }
    }
}

if (-not $modelDataArgs) {
    Write-Host "ERROR: tiny.en model was not found. ZIP 배포에 필요한 모델을 먼저 준비하세요." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$distName = "LocalSTT_light"
$zipName = "$distName.zip"

& $pythonExe -m PyInstaller `
  --onedir `
  --windowed `
  --clean `
  --name $distName `
  @modelDataArgs `
  --hidden-import=faster_whisper `
  --hidden-import=sounddevice `
  --hidden-import=soundcard `
  --collect-all faster_whisper `
  --collect-all soundcard `
  --collect-all sounddevice `
  --exclude-module torch.utils.tensorboard `
  --exclude-module tensorboard `
  main.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Build failed!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$distPath = Join-Path $currentDir "dist\$distName"
if (Test-Path $zipName) {
    Remove-Item -Force $zipName -ErrorAction SilentlyContinue
}

Write-Host "Creating ZIP package: $zipName" -ForegroundColor Green
Compress-Archive -Path $distPath\* -DestinationPath $zipName -Force

Write-Host ""
Write-Host "Build completed: $distPath" -ForegroundColor Green
Write-Host "Package created: $currentDir\$zipName" -ForegroundColor Green
Read-Host "Press Enter to exit"
