@echo off
title SSK Footwear - ERP Local Development
echo ==========================================================
echo Starting SSK Footwear ERP (Frontend and Backend) ...
echo ==========================================================

:: Get root directory of the script
set "ROOT_DIR=%~dp0"

:: Start backend in a separate terminal window
echo [1/2] Starting backend FastAPI server...
start "SSK ERP Backend (FastAPI)" cmd /k "cd /d %ROOT_DIR%backend && .venv\Scripts\activate && uvicorn server:app --reload --port 8000"

:: Start frontend in a separate terminal window
echo [2/2] Starting frontend React server...
start "SSK ERP Frontend (React)" cmd /k "cd /d %ROOT_DIR%frontend && npm start"

echo ==========================================================
echo Both servers have been launched in separate windows!
echo Backend is running at http://localhost:8000
echo Frontend is launching...
echo ==========================================================
pause
