@echo off
chcp 65001 >nul
echo ========================================
echo   PowerShellFileTools - Build Script
echo ========================================
echo.

:: Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller
    echo.
)

:: Install dependencies
echo [INFO] Installing dependencies...
pip install -r requirements.txt
echo.

:: Build
echo [INFO] Building PowerShellFileTools...
pyinstaller --noconfirm ^
    --name PowerShellFileTools ^
    --windowed ^
    --onedir ^
    --add-data "ui;ui" ^
    --add-data "core;core" ^
    --hidden-import pywebview ^
    --hidden-import psutil ^
    --collect-all pywebview ^
    main.py

echo.
if errorlevel 1 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo ========================================
echo   Build Successful!
echo   Output: dist\PowerShellFileTools\
echo ========================================
echo.
echo To register context menu, run:
echo   dist\PowerShellFileTools\PowerShellFileTools.exe --install
echo.
pause
