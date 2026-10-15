@echo off
cd /d "%~dp0"
title [DEV] Gambit - poster & thumbnail studio (port 5100)
if not exist .venv (
  echo Pehli baar setup ho raha hai...
  python -m venv .venv || (echo Python nahi mila. python.org se Python 3.10+ install karo, Add to PATH tick karna. & pause & exit /b)
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
start "" http://localhost:5100
python app.py
pause
