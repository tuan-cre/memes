"""Platform detection, tool checking, notifications, debug logging."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


_DEBUG = False


def _platform() -> str:
    if sys.platform == "linux":
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return sys.platform


def _tool_available(name: str) -> bool:
    """Check if an executable exists on PATH."""
    return shutil.which(name) is not None


def _debug(msg: str) -> None:
    """Print debug message to stderr when --debug is enabled."""
    if _DEBUG:
        print(f"[debug] {msg}", file=sys.stderr)


def _notify(title: str, message: str, icon: Path | None = None) -> None:
    """Cross-platform desktop notification."""
    # Try plyer first (works on all platforms)
    try:
        from plyer import notification  # type: ignore[import-untyped]
        notification.notify(
            title=title,
            message=message,
            app_name="Meme Collection",
            timeout=4,
        )
        return
    except Exception:
        pass

    platform = _platform()
    if platform == "linux":
        args = ["notify-send", title, message]
        if icon:
            args[1:1] = ["-i", str(icon)]
        try:
            subprocess.run(args, check=False)
        except FileNotFoundError:
            pass
    elif platform == "macos":
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                check=False,
            )
        except FileNotFoundError:
            pass

    # Fallback: print to stderr
    print(f"[{title}] {message}", file=sys.stderr)
