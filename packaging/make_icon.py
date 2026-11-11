"""
Generates the application icon used by the Windows executable, the installer
and the Linux desktop entry.

Run with the same Python interpreter that has PyQt6 installed:

    python packaging/make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt6.QtCore import QBuffer, QIODevice  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

from icon_generator import render_icon_pixmap  # noqa: E402

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(pixmap) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


def write_ico(path: str, images) -> None:
    """Writes a PNG-compressed multi-resolution ICO (Windows Vista+)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    payload = b""
    for size, data in images:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
        payload += data
    with open(path, "wb") as fh:
        fh.write(header + entries + payload)


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841

    images = []
    for size in ICO_SIZES:
        pixmap = render_icon_pixmap(
            size=size, volume=12, is_connected=True, light_mode=2, with_background=True
        )
        images.append((size, png_bytes(pixmap)))

    ico_path = os.path.join(ROOT, "packaging", "app.ico")
    write_ico(ico_path, images)

    png_path = os.path.join(ROOT, "packaging", "app.png")
    render_icon_pixmap(
        size=256, volume=12, is_connected=True, light_mode=2, with_background=True
    ).save(png_path, "PNG")

    print("wrote %s (%d bytes)" % (ico_path, os.path.getsize(ico_path)))
    print("wrote %s (%d bytes)" % (png_path, os.path.getsize(png_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
