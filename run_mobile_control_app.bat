@echo off
cd /d "%~dp0"
if not exist .env (
    echo ERROR: .env file not found!
    echo Copy .env.example to .env and add your credentials:
    echo   copy .env.example .env
    echo.
    exit /b 1
)
echo ============================================
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=*" %%b in ("%%a") do (
        echo Mobile access: http://%%b:5055
    )
)
echo ============================================
py mobile_control_app.py
