#!/bin/bash
# MTG Commander Deck Tester - macOS launcher.
# Double-click this file (first time: see "macOS" in README.md), or run:  bash start-mac.command
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed."
  echo "Install it from https://www.python.org/downloads/macos/ and start this file again."
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "Python 3.9 or newer is needed. Install it from https://www.python.org/downloads/macos/"
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "First start: setting things up (about a minute)..."
  python3 -m venv .venv || { echo "Could not create the Python environment."; read -n 1 -s -r; exit 1; }
fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
  echo "Installing required packages..."
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt \
    || { echo "Installing packages failed. Check your internet connection and try again."; read -n 1 -s -r; exit 1; }
  cp requirements.txt .venv/requirements.installed
fi

.venv/bin/python -m mtg_deck_tester "$@"
