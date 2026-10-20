$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$buildScript = Join-Path $projectRoot "build_windows.bat"

if (-not (Test-Path -LiteralPath $buildScript -PathType Leaf)) {
    throw "build_windows.bat is missing. Reapply the Sketch2GUI OCR/icon update."
}

Push-Location $projectRoot
try {
    Write-Host "Running syntax checks, tests, and the OCR-enabled Windows build..."
    & $env:ComSpec /d /c "`"$buildScript`""
    if ($LASTEXITCODE -ne 0) {
        throw "build_windows.bat failed (exit $LASTEXITCODE). The release ZIP was not created."
    }

    $distribution = Join-Path $projectRoot "dist\Sketch2GUI"
    $executable = Join-Path $distribution "Sketch2GUI.exe"
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "Expected executable missing: $executable"
    }

    $internal = Join-Path $distribution "_internal"
    if (-not (Test-Path (Join-Path $internal "paddleocr")) -and -not (Test-Path (Join-Path $distribution "paddleocr"))) {
        throw "PaddleOCR was not found in the packaged application. Refusing to create a release ZIP."
    }
    if (-not (Test-Path (Join-Path $internal "paddle")) -and -not (Test-Path (Join-Path $distribution "paddle"))) {
        throw "PaddlePaddle was not found in the packaged application. Refusing to create a release ZIP."
    }
    if (-not (Test-Path (Join-Path $internal "assets\app_icon.ico")) -and -not (Test-Path (Join-Path $distribution "assets\app_icon.ico"))) {
        throw "Application icon data is missing from the package. Refusing to create a release ZIP."
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $archive = Join-Path (Join-Path $projectRoot "dist") "Sketch2GUI-Windows-OCR-$timestamp.zip"
    Compress-Archive -Path (Join-Path $distribution "*") -DestinationPath $archive -CompressionLevel Optimal
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    $checksumFile = "$archive.sha256"
    "{0}  {1}" -f $hash, (Split-Path -Leaf $archive) |
        Set-Content -LiteralPath $checksumFile -Encoding ascii

    Write-Host ""
    Write-Host "OCR-enabled release package created." -ForegroundColor Green
    Write-Host "Application: $executable"
    Write-Host "Full folder: $distribution"
    Write-Host "Release ZIP: $archive"
    Write-Host "SHA-256: $hash"
    Write-Host "Checksum file: $checksumFile"
    Write-Host "The PaddleOCR/PaddlePaddle runtime is packaged. Model weights download on first OCR use and require internet access."
    Write-Host "Launch and test the packaged EXE, including an actual OCR inference, before distributing it."
}
finally {
    Pop-Location
}
