#!/usr/bin/env sh
# Starts the Edifier R20 tray controller in the background (source checkout).
set -eu
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
    exec python3 run.py "$@"
fi
echo "python3 was not found. Install Python 3.10+ (or use scripts/install_linux.sh)." >&2
exit 1
