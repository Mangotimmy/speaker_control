"""
Detached background launcher for the Edifier R20 tray controller.

This replaces the old ``start_tray.vbs``.  VBScript/``wscript`` is an optional
Windows feature that is disabled on many managed machines (and Microsoft is
phasing it out), so the app is started by re-launching ``pythonw`` directly with
``DETACHED_PROCESS`` instead.

Usage:
    python run.py            start the tray app in the background
    python run.py --autostart
"""

from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import platform_utils


def main() -> int:
    if platform_utils.is_frozen():
        print("run.py is only needed when starting from source; use the packaged app.")
        return 0

    args = platform_utils.start_command() + list(sys.argv[1:])
    process = platform_utils.spawn_detached(args, cwd=SCRIPT_DIR)
    print(
        "Started Edifier R20 tray app (pid %s).\nLogs: %s"
        % (process.pid, platform_utils.log_dir())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
