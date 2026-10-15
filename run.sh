#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
( sleep 2; (open http://localhost:5100 || xdg-open http://localhost:5100) >/dev/null 2>&1 ) &
python app.py
