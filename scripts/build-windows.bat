@echo off
echo === Agent Studio Windows Build ===
echo.

echo [1/3] Building Python backend...
pip install pyinstaller --quiet
python backend/build_backend.py
if errorlevel 1 (
    echo ERROR: Backend build failed
    exit /b 1
)
echo Backend built: dist\backend\agent-studio-backend.exe
echo.

echo [2/3] Building frontend...
cd frontend
call npm install --silent
call npm run build
if errorlevel 1 (
    cd ..
    echo ERROR: Frontend build failed
    exit /b 1
)
cd ..
echo Frontend built: dist\frontend\
echo.

echo [3/3] Building Electron installer...
cd electron
call npm install --silent
call npm run build
if errorlevel 1 (
    cd ..
    echo ERROR: Electron build failed
    exit /b 1
)
cd ..
echo.
echo === Build complete! ===
echo Installer: dist\electron\Agent Studio Setup *.exe
pause
