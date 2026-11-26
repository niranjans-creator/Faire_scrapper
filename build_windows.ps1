$ErrorActionPreference = "Stop"

if (-not (Test-Path .venv)) {
    py -3 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt pywebview pyinstaller
& .\.venv\Scripts\python.exe -m playwright install chromium
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean faire_scraper.spec

Write-Host "Built dist\FaireScraper\FaireScraper.exe"
