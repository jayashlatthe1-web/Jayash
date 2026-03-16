Push-Location $PSScriptRoot
if (-Not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
.
# Ensure dependencies are installed (no harm if already satisfied)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Run the application with the venv python
.\.venv\Scripts\python.exe app.py
Pop-Location
