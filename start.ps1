$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Se necesita Python 3.11 o superior." }
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Instala Python 3.11 o superior y crea .venv manualmente." }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias." }
& .\.venv\Scripts\python.exe -m streamlit run app.py
