@echo off
title SSK Footwear - ERP Local Development
echo ==========================================================
echo Starting SSK Footwear ERP (MongoDB, Backend, Frontend)...
echo ==========================================================

:: Get root directory of the script
set "ROOT_DIR=%~dp0"

:: Check and start local Supabase via Docker
echo [0/4] Checking local Supabase (Docker)...
cmd /c "npx supabase status >nul 2>&1 || npx supabase start"

:: Start MongoDB in a separate terminal window
echo [1/4] Starting MongoDB database server...
start "SSK ERP MongoDB" cmd /k "cd /d %ROOT_DIR%mongodb-portable\mongodb-win32-x86_64-windows-7.0.6\bin && mongod.exe --dbpath %ROOT_DIR%mongodb-portable\data"

:: Start backend in a separate terminal window
echo [2/4] Starting backend FastAPI server...
start "SSK ERP Backend (FastAPI)" cmd /k "cd /d %ROOT_DIR%backend && .venv\Scripts\activate && uvicorn server:app --reload --host 0.0.0.0 --port 8000"

:: Start frontend in a separate terminal window
echo [3/4] Starting frontend React server...
start "SSK ERP Frontend (React)" cmd /k "cd /d %ROOT_DIR%frontend && cmd /c npm start"

echo ==========================================================
echo All servers (Local Supabase, MongoDB, FastAPI Backend, React Frontend) launched!
echo Backend is running at http://localhost:8000
echo Frontend is launching at http://localhost:3000
echo Local Supabase Studio at http://localhost:54323
echo ==========================================================

