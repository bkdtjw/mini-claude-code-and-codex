#!/bin/bash
# Agent Studio Linux Build Script

set -e

echo "=== Agent Studio Linux Build ==="
echo ""

echo "[1/3] Building Python backend..."
pip install pyinstaller --quiet
python backend/build_backend.py
if [ $? -ne 0 ]; then
    echo "ERROR: Backend build failed"
    exit 1
fi
echo "Backend built: dist/backend/agent-studio-backend"
echo ""

echo "[2/3] Building frontend..."
cd frontend
npm install --silent
npm run build
if [ $? -ne 0 ]; then
    cd ..
    echo "ERROR: Frontend build failed"
    exit 1
fi
cd ..
echo "Frontend built: dist/frontend/"
echo ""

echo "[3/3] Build complete!"
echo "Note: Electron installer is only supported on Windows"
echo "To run the application:"
echo "  - Backend: python -m backend.main"
echo "  - Frontend: cd frontend && npm run dev"
echo "  - Or use: npm run dev (backend) and npm run dev-frontend (frontend)"
