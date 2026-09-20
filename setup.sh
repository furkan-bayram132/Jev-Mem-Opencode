#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 11), "Jev-Mem requires Python 3.11+"'
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
if [ ! -f .env ]; then
    (umask 077; cp .env.example .env)
fi
echo 'Jev-Mem is ready. Activate with: source .venv/bin/activate'
echo 'Try the offline demo: python jev_mem_demo.py'
echo 'For live runs, add your own TypeSafe and OpenAI/Azure keys to .env.'
