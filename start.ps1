$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or later is required." }
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Install Python 3.11 or later and create .venv manually." }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependencies could not be installed." }
& .\.venv\Scripts\python.exe -m streamlit run app.py
