# Quick launch for the unified roll-forming workflow.
Set-Location $PSScriptRoot
if (-not (Test-Path .\.venv\Scripts\Activate.ps1)) {
    Write-Error "Missing .venv. Run: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}
& .\.venv\Scripts\Activate.ps1
streamlit run app.py
