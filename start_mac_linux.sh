#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
[ -f backend/.env ] || cp backend/.env.example backend/.env
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt
(cd frontend && npm install && npm run dev) &
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
