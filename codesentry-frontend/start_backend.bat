@echo off
echo Starting CodeSentry Backend...
cd /d "%~dp0backend"
pip install -r requirements.txt -q
uvicorn main:app --reload --port 8000
