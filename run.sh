#!/usr/bin/env sh
# Starts Clipper. First run creates a virtual environment and installs dependencies.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Setting up Clipper for the first time..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -m playwright install chromium
fi
exec .venv/bin/python -m clipper "$@"
