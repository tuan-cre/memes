"""Clipboard operations: copy images to clipboard, save from clipboard."""
from __future__ import annotations

import base64
import subprocess
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

from meme.config import MEME_DIR
from meme.platform import _notify, _platform, _tool_available
from meme.server_client import _upload_if_remote


# ── Copy image TO clipboard ──────────────────────────────────────────────────


def _copy_image(path: Path) -> bool:
    """Copy a PNG image to the system clipboard."""
    platform = _platform()
    if platform == "linux":
        for tool, args in [
            ("wl-copy", ["wl-copy", "--type", "image/png"]),
            ("xclip", ["xclip", "-selection", "clipboard", "-t", "image/png"]),
        ]:
            if _tool_available(tool):
                try:
                    with open(path, "rb") as f:
                        subprocess.run(args, stdin=f, check=True)
                    return True
                except subprocess.CalledProcessError:
                    continue
        return False

    if platform == "macos":
        try:
            from PIL import Image as PILImage
            img = PILImage.open(path)
            w, h = img.size
            raw = img.tobytes()
            script = (
                "set theImage to (open for access POSIX file "
                f"\"{path}\")\n"
                "set clipboard to (read theImage as PNG picture)\n"
                "close access theImage"
            )
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return True
        except Exception:
            # Fallback: PIL clipboard grab
            try:
                from PIL import ImageGrab
                img = Image.open(path)
                # macOS doesn't have a reliable PIL clipboard set,
                # so this always fails — fall through to print save path
                return False
            except Exception:
                return False

    # Windows — no clipboard set without win32clipboard
    return False


# ── Save image FROM clipboard ────────────────────────────────────────────────


def _clipboard_image_pil(filepath: Path) -> bool:
    """Read clipboard using PIL (macOS/Windows)."""
    try:
        from PIL import ImageGrab  # type: ignore[import-untyped]
        img = ImageGrab.grab()
        if img is None:
            return False
        img.save(filepath, "PNG")
        return True
    except Exception:
        return False


def cmd_from_clip() -> int:
    """Save clipboard image to collection."""
    MEME_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    filepath = MEME_DIR / f"meme_{timestamp}.png"
    platform = _platform()

    saved = False

    if platform == "linux":
        for tool in [
            ["wl-paste", "--type", "image/png"],
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
        ]:
            try:
                data = subprocess.run(tool, capture_output=True, check=True)
                if len(data.stdout) > 0:
                    filepath.write_bytes(data.stdout)
                    saved = True
                    break
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue

    elif platform == "macos":
        # Try PIL clipboard grab first
        if _clipboard_image_pil(filepath):
            saved = True
        else:
            # Fallback: osascript + base64
            try:
                script = (
                    "set imgData to the clipboard as «class PNGf»\n"
                    "set bytes to {id} of imgData\n"
                    "set astid to AppleScript's text item delimiters\n"
                    "set AppleScript's text item delimiters to {', '}\n"
                    "set byteList to bytes as text\n"
                    "set AppleScript's text item delimiters to astid\n"
                    "return byteList"
                )
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    byte_values = [
                        int(b) for b in result.stdout.strip().split(", ")
                        if b.strip().isdigit()
                    ]
                    filepath.write_bytes(bytes(byte_values))
                    saved = True
            except Exception:
                pass

    elif platform == "windows":
        # Windows — try PIL clipboard
        try:
            from PIL import ImageGrab  # type: ignore[import-untyped]
            img = ImageGrab.grab()
            if img is not None:
                img.save(filepath, "PNG")
                saved = True
        except Exception:
            pass

    if not saved:
        _notify("Meme Collection", "No image in clipboard")
        return 1

    _copy_image(filepath)
    _notify("Meme Collection", f"From clipboard: {filepath.name}", icon=filepath)
    _upload_if_remote(filepath)
    return 0
