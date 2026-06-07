"""Native messaging host protocol (browser extension)."""
from __future__ import annotations

import base64
import json
import struct
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

from meme.config import MEME_DIR
from meme.platform import _notify
from meme.clipboard import _copy_image


def _read_native_msg() -> dict:
    raw = sys.stdin.buffer.read(4)
    if not raw or len(raw) < 4:
        return {}
    length = struct.unpack("<I", raw)[0]
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def _send_native_msg(message: dict) -> None:
    encoded = json.dumps(message).encode("utf-8")
    stdout = sys.stdout.buffer
    stdout.write(struct.pack("<I", len(encoded)))
    stdout.write(encoded)
    stdout.flush()


def _save_native_image(data_b64: str) -> dict:
    try:
        img = Image.open(BytesIO(base64.b64decode(data_b64)))
        buf = BytesIO()
        img.save(buf, "PNG")
        png_data = buf.getvalue()

        filename = f"meme_{int(__import__('time').time())}.png"
        filepath = MEME_DIR / filename
        MEME_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(png_data)

        _copy_image(filepath)
        _notify("Meme Collection", f"Saved: {filename}", icon=filepath)
        return {"success": True, "filename": filename}
    except Exception as e:
        return {"success": False, "error": str(e)}


def cmd_native_host() -> int:
    """Native messaging host mode — communicates with browser extension."""
    msg = _read_native_msg()
    action = msg.get("action", "")
    if action == "save":
        data_b64 = msg.get("data", "")
        response = _save_native_image(data_b64)
    else:
        response = {"success": False, "error": f"Unknown action: {action}"}
    _send_native_msg(response)
    return 0
