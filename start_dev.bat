@echo off
title SSK Footwear - ERP Local Development
echo ==========================================================
echo Starting SSK Footwear ERP (Frontend and Backend) ...
echo ==========================================================

:: Get root directory of the script
set "ROOT_DIR=%~dp0"

:: Prepend portable runtimes to local path for commands run from this batch
set "PATH=%ROOT_DIR%node-portable\node-v22.11.0-win-x64;%ROOT_DIR%python-portable;%PATH%"

:: Start backend in a separate terminal window
echo [1/2] Starting backend FastAPI server...
start "SSK ERP Backend (FastAPI)" cmd /k "set PATH=%ROOT_DIR%python-portable;%PATH% && cd /d %ROOT_DIR%backend && .venv\Scripts\activate && uvicorn server:app --reload --port 8000"

:: Start frontend in a separate terminal window
echo [2/2] Starting frontend React server...
start "SSK ERP Frontend (React)" cmd /k "set PATH=%ROOT_DIR%node-portable\node-v22.11.0-win-x64;%PATH% && set BROWSER=none && cd /d %ROOT_DIR%frontend && npm.cmd start"

echo ==========================================================
echo Both servers have been launched in separate windows!
echo Backend is running at http://localhost:8000
echo Frontend is launching...
echo ==========================================================

