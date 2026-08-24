## Backend regression on Windows

Backend Python commands MUST run with `backend` as the working directory.

From repository root:

```powershell
Push-Location backend

& ".\.venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider
& ".\.venv\Scripts\python.exe" -m pip check

Pop-Location