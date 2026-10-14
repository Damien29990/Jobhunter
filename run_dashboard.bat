@echo off
REM ============================================================
REM  Jobhunter — one .bat starts backend (:8000) and frontend (:5173).
REM  Double-click this file. The API window is the same script with "api".
REM ============================================================
cd /d "%~dp0"

if /I "%~1"=="api" goto :start_api

setlocal enabledelayedexpansion
set "CONDA_ENV=jobhunter"
set "CONDA_OK=0"

echo.
echo [run_dashboard] Jobhunter Pixel Office Dashboard
echo [run_dashboard] ================================
echo.

call conda activate %CONDA_ENV% 2>nul && set "CONDA_OK=1"
if "!CONDA_OK!"=="0" if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
  echo [run_dashboard] activating via Anaconda...
  call "%USERPROFILE%\anaconda3\Scripts\activate.bat" %CONDA_ENV% && set "CONDA_OK=1"
)
if "!CONDA_OK!"=="0" if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
  echo [run_dashboard] activating via Miniconda...
  call "%USERPROFILE%\miniconda3\Scripts\activate.bat" %CONDA_ENV% && set "CONDA_OK=1"
)
if "!CONDA_OK!"=="0" (
  echo [run_dashboard] WARNING: could not activate conda env '%CONDA_ENV%'.
  echo [run_dashboard]          Continuing with the current Python on PATH ^(if any^).
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

echo.
echo [run_dashboard] Installing backend deps if needed...
python -m pip install -q -r src\api\requirements.txt
if errorlevel 1 (
  echo [run_dashboard] ERROR: backend pip install failed.
  pause
  exit /b 1
)

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

echo.
echo [run_dashboard] Starting FastAPI backend on http://127.0.0.1:8000 ...
start "Jobhunter API" cmd /k "%~f0" api

echo [run_dashboard] Starting Vite frontend on http://localhost:5173 ...
echo [run_dashboard] Open http://localhost:5173 in your browser.
echo [run_dashboard] Close this window to stop the frontend. Close "Jobhunter API" to stop the backend.
echo.
pushd frontend
call npm run dev
popd
endlocal
exit /b 0

:start_api
REM Same file, API window only. New cmd does not inherit conda.
call conda activate jobhunter 2>nul
if /I not "%CONDA_DEFAULT_ENV%"=="jobhunter" (
  if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" jobhunter
  )
)
if /I not "%CONDA_DEFAULT_ENV%"=="jobhunter" (
  if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
    call "%USERPROFILE%\anaconda3\Scripts\activate.bat" jobhunter
  )
)
if /I not "%CONDA_DEFAULT_ENV%"=="jobhunter" (
  echo [run_dashboard] ERROR: could not activate conda env jobhunter.
  echo [run_dashboard] conda activate jobhunter ^&^& python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
  pause
  exit /b 1
)
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo [run_dashboard] CONDA_DEFAULT_ENV=%CONDA_DEFAULT_ENV%
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
