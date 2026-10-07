#!/usr/bin/env sh
# Starts Clipper. First run creates a virtual environment and installs dependencies.
# Safe to run again at any time: it updates the code and replaces a Clipper that's already running.
cd "$(dirname "$0")" || exit 1

# Stay up to date with GitHub (skipped quietly if offline or if you have local commits).
if [ -d .git ] && command -v git >/dev/null 2>&1; then
  git pull --ff-only --quiet 2>/dev/null || echo "Note: couldn't auto-update from GitHub; starting the version you have."
fi

if [ ! -x .venv/bin/python ]; then
  echo "Setting up Clipper for the first time (a few minutes)..."
  if ! python3 -m venv .venv; then
    rm -rf .venv
    echo "Could not create a Python environment. On Ubuntu/Debian run:  sudo apt install python3-venv python3-pip"
    exit 1
  fi
  .venv/bin/python -m pip install --upgrade pip || exit 1
  if ! .venv/bin/python -m pip install -r requirements.txt; then
    rm -rf .venv
    echo "Installing dependencies failed — see the error above."
    exit 1
  fi
  .venv/bin/python -m playwright install chromium
elif ! .venv/bin/python -c "import fastapi, playwright" 2>/dev/null || [ requirements.txt -nt .venv/.installed ]; then
  echo "Updating dependencies..."
  .venv/bin/python -m pip install -q -r requirements.txt || exit 1
fi
touch .venv/.installed

# Kokoro (natural voice) is optional: it needs Python 3.10-3.12. CPU-only PyTorch keeps it small and leaves the GPU to ComfyUI.
if ! .venv/bin/python -c "import kokoro" 2>/dev/null && [ ! -f .venv/.kokoro-tried ]; then
  echo "Installing the Kokoro voice (one time, a few minutes)..."
  if .venv/bin/python -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu \
     && .venv/bin/python -m pip install -q "kokoro>=0.9.4"; then
    .venv/bin/python -m spacy download en_core_web_sm >/dev/null 2>&1 || true  # otherwise fetched on first use
    echo "Kokoro installed."
  else
    echo "Note: Kokoro couldn't be installed (it needs Python 3.10-3.12). Piper and the system voice still work."
  fi
  touch .venv/.kokoro-tried
fi

exec .venv/bin/python -m clipper "$@"
