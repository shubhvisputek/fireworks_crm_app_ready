#!/bin/sh
# Fireworks CRM launcher for Linux and macOS. With no options it shows the requirements and a menu;
# any options go straight to fireworks.py (try: ./start.sh help, ./start.sh start --network).
cd "$(dirname "$0")" || exit 1
export FIREWORKS_LAUNCHER="./start.sh"
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    exec "$py" fireworks.py "$@"
  fi
done
echo "Fireworks CRM needs Python 3.10 or newer."
echo "  macOS:          brew install python   (or download from https://www.python.org/downloads/)"
echo "  Ubuntu/Debian:  sudo apt install python3 python3-venv python3-pip"
echo "  Fedora:         sudo dnf install python3 python3-pip"
exit 1
