#!/usr/bin/env sh
# Stops the Edifier R20 tray controller (source checkout or installed build).
pkill -f 'EdifierR20Tray' 2>/dev/null || true
pkill -f 'tray_app.py' 2>/dev/null || true
echo "Edifier R20 tray app stopped."
