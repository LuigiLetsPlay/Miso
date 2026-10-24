# Builds dist\Miso\Miso.exe and (if Inno Setup is installed) dist\Miso-Setup.exe
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller
.\.venv\Scripts\python.exe tools\make_icon.py
.\.venv\Scripts\python.exe tools\version_info.py
# no UPX: packed executables trigger far more antivirus false positives
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --noupx --name Miso `
    --icon assets\icon.ico --version-file build\version_info.txt --add-data "assets;assets" Miso.pyw
Copy-Item LICENSE dist\Miso\LICENSE.txt -Force
Copy-Item THIRD_PARTY_NOTICES.md dist\Miso\ -Force
Write-Host "Fertig: dist\Miso\Miso.exe"

if (Test-Path dist\Miso-portable.zip) { Remove-Item dist\Miso-portable.zip }
Compress-Archive -Path dist\Miso -DestinationPath dist\Miso-portable.zip -CompressionLevel Optimal
Write-Host "Fertig: dist\Miso-portable.zip"

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    $version = (.\.venv\Scripts\python.exe -c "import miso; print(miso.__version__)").Trim()
    & $iscc /Q "/DAppVersion=$version" installer\miso.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup ist fehlgeschlagen" }
    Write-Host "Fertig: dist\Miso-Setup.exe"
} else {
    Write-Host "Inno Setup nicht gefunden, Setup wird übersprungen (https://jrsoftware.org/isinfo.php)"
}
