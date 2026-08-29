@echo off
setlocal

set "COMPOSE_DIR=%~dp0"
set "HEALTH_URL=http://localhost:8002/health"
set "FRONTEND_URL=http://localhost:3002"
set "MAX_WAIT=120"

echo InterScribe starting...

rem ── Check if already running ────────────────────────────────────────────────
curl -sf %HEALTH_URL% >nul 2>&1
if %errorlevel% equ 0 (
    echo Already running.
    start "" "%FRONTEND_URL%"
    exit /b 0
)

rem ── Wait for Docker engine ───────────────────────────────────────────────────
echo Waiting for Docker engine...
set /a waited=0
:waitdocker
docker info >nul 2>&1
if %errorlevel% equ 0 goto dockerready
if %waited% geq %MAX_WAIT% (
    echo ERROR: Docker engine did not start within %MAX_WAIT%s. Is Docker Desktop installed?
    exit /b 1
)
timeout /t 5 /nobreak >nul
set /a waited+=5
goto waitdocker

:dockerready
echo Docker ready. Starting containers...

rem ── Start containers ─────────────────────────────────────────────────────────
pushd "%COMPOSE_DIR%"
docker compose up -d
if %errorlevel% neq 0 (
    echo ERROR: docker compose up failed.
    popd
    exit /b 1
)
popd

rem ── Wait for backend health ──────────────────────────────────────────────────
echo Waiting for InterScribe to be ready...
set /a waited=0
:waithealth
curl -sf %HEALTH_URL% >nul 2>&1
if %errorlevel% equ 0 goto healthy
if %waited% geq %MAX_WAIT% (
    echo ERROR: Backend did not become healthy within %MAX_WAIT%s.
    exit /b 1
)
timeout /t 5 /nobreak >nul
set /a waited+=5
goto waithealth

:healthy
echo InterScribe ready. Opening browser...
start "" "%FRONTEND_URL%"
exit /b 0
