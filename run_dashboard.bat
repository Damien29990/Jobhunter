@echo off
REM ============================================================
REM  Jobhunter Pixel Office Dashboard launcher (Windows cmd)
REM  Starts the FastAPI backend (:8000) and Vite frontend (:5173).
REM  Close this window (or Ctrl+C) to stop the frontend.
REM  The backend runs in a separate window titled "Jobhunter API".
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo [run_dashboard] Jobhunter Pixel Office Dashboard
echo [run_dashboard] ================================
echo.

REM ---- 1. Activate conda env 'jobhunter' (try several methods) ----
set "CONDA_ENV=jobhunter"
set "CONDA_OK=0"

REM Method A: conda already initialized in this shell
call conda activate %CONDA_ENV% 2>nul && set "CONDA_OK=1"

REM Method B: Anaconda install
if "!CONDA_OK!"=="0" if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
  echo [run_dashboard] activating via Anaconda...
  call "%USERPROFILE%\anaconda3\Scripts\activate.bat" %CONDA_ENV% && set "CONDA_OK=1"
)

REM Method C: Miniconda install
if "!CONDA_OK!"=="0" if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
  echo [run_dashboard] activating via Miniconda...
  call "%USERPROFILE%\miniconda3\Scripts\activate.bat" %CONDA_ENV% && set "CONDA_OK=1"
)

if "!CONDA_OK!"=="0" (
  echo [run_dashboard] WARNING: could not activate conda env '%CONDA_ENV%'.
  echo [run_dashboard]          Continuing with the current Python on PATH ^(if any^).
  echo [run_dashboard]          If python is missing, open an "Anaconda Prompt", run `conda activate jobhunter`,
  echo [run_dashboard]          then run this .bat from there.
)

echo.
echo [run_dashboard] Checking python...
where python >nul 2>nul
if errorlevel 1 (
  echo [run_dashboard] ERROR: python not found. Activate the jobhunter conda env first.
  pause
  exit /b 1
)
python --version

REM ---- 2. Backend deps ----
echo.
echo [run_dashboard] Installing backend deps if needed...
python -m pip install -q -r src\api\requirements.txt
if errorlevel 1 (
  echo [run_dashboard] ERROR: backend pip install failed.
  pause
  exit /b 1
)

REM ---- 3. Frontend deps ----
echo.
if not exist "frontend\node_modules" (
  echo [run_dashboard] Installing frontend deps ^(first run, may take a minute^)...
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [run_dashboard] ERROR: npm not found. Install Node.js 20.9+ first.
    pause
    exit /b 1
  )
  pushd frontend
  call npm install
  if errorlevel 1 (
    echo [run_dashboard] ERROR: npm install failed.
    popd
    pause
    exit /b 1
  )
  popd
) else (
  echo [run_dashboard] frontend deps already installed.
)

REM ---- 4. Launch both ----
echo.
echo [run_dashboard] Starting FastAPI backend on http://127.0.0.1:8000 ...
start "Jobhunter API" cmd /k "cd /d %~dp0 && set PYTHONUTF8=1 && set PYTHONIOENCODING=utf-8 && python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload"

echo [run_dashboard] Starting Vite frontend on http://localhost:5173 ...
echo [run_dashboard] Open http://localhost:5173 in your browser.
echo [run_dashboard] (Close the "Jobhunter API" window to stop the backend.)
echo.
pushd frontend
call npm run dev
popd

endlocal
