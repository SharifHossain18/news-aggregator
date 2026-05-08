@echo off
cd /d "%~dp0"
if not exist .env (
    echo ERROR: .env file not found!
    echo Copy .env.example to .env and add your credentials:
    echo   copy .env.example .env
    echo.
    exit /b 1
)
py mobile_control_app.py
