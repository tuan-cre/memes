"""Screen capture — grim+slurp (Wayland), mss (X11/Win/Mac)."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from meme.config import MEME_DIR
from meme.platform import _debug, _notify, _platform, _tool_available
from meme.server_client import _upload_if_remote
from meme.clipboard import _copy_image


def cmd_capture(monitor: int | None = None) -> int:
    """Capture a screen region and save to collection."""
    MEME_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    final_path = MEME_DIR / f"meme_{timestamp}.png"

    # Write to temp — never directly to final path.  If capture fails
    # partway, the temp is cleaned up and no 0-byte orphan pollutes
    # the collection.
    fd, tmp_str = tempfile.mkstemp(suffix=".png", dir=str(MEME_DIR))
    os.close(fd)
    tmp = Path(tmp_str)

    try:
        ok = _capture_to(tmp, monitor=monitor)
        _debug(f"capture_to returned ok={ok!r}")

        if ok and tmp.exists() and tmp.stat().st_size > 0:
            sz = tmp.stat().st_size
            _debug(f"rename: tmp exists (size={sz}) -> {final_path.name}")
            tmp.rename(final_path)
        elif ok is None:  # user cancelled
            return 0
        else:
            sz = tmp.stat().st_size if tmp.exists() else -1
            _debug(f"failure: ok={ok!r}, tmp_exists={tmp.exists()}, tmp_size={sz}")
            _notify("Meme Collection", "Capture failed")
            return 1
    finally:
        tmp.unlink(missing_ok=True)

    _copy_image(final_path)
    _notify("Meme Collection", f"Captured: {final_path.name}", icon=final_path)

    _upload_if_remote(final_path)
    return 0


def _capture_to(path: Path, monitor: int | None = None) -> bool | None:
    """Capture to *path*.  Returns True=ok, None=cancelled, False=error."""
    platform = _platform()
    _debug(f"platform={platform}, monitor={monitor}, path={path}")

    if platform == "linux":
        # ── grim + slurp: native Wayland (wlr-screencopy) ──
        has_slurp = _tool_available("slurp")
        has_grim = _tool_available("grim")
        _debug(f"slurp={has_slurp}, grim={has_grim}")

        if has_slurp and has_grim:
            _debug("path: grim+slurp (native Wayland)")
            region = subprocess.run(["slurp"], capture_output=True, text=True)
            _debug(f"slurp rc={region.returncode}, stdout={region.stdout.strip()!r}")
            if region.returncode != 0:
                return None  # user cancelled
            result = subprocess.run(
                ["grim", "-g", region.stdout.strip(), str(path)],
                capture_output=True, text=True,
            )
            _debug(f"grim rc={result.returncode}")
            if result.returncode != 0:
                _debug(f"grim stderr: {result.stderr.strip() if result.stderr else '(none)'}")
            ok = result.returncode == 0 and path.exists() and path.stat().st_size > 0
            _debug(f"grim result: {'ok' if ok else 'FAILED'} (size={path.stat().st_size if path.exists() else 0})")
            return ok

        # ── slurp (interaction) + mss (capture) ──
        if has_slurp:
            _debug("path: slurp+mss (grim not found)")
            region = subprocess.run(["slurp"], capture_output=True, text=True)
            _debug(f"slurp rc={region.returncode}, stdout={region.stdout.strip()!r}")
            if region.returncode != 0:
                return None  # user cancelled
            m = re.match(r"(\d+),(\d+)\s+(\d+)x(\d+)", region.stdout.strip())
            if m:
                x, y, w, h = map(int, m.groups())
                _debug(f"region: {x},{y} {w}x{h}")
                return _capture_mss(path, {"left": x, "top": y, "width": w, "height": h})
            _debug(f"slurp output did not match expected pattern: {region.stdout.strip()!r}")
        # ── mss full-screen fallback (X11 / portals) ──
        _debug("path: mss full-screen fallback")
        return _capture_mss(path, monitor=monitor)

    elif platform == "macos":
        has_scr = _tool_available("screencapture")
        _debug(f"screencapture={has_scr}")
        if has_scr:
            result = subprocess.run(["screencapture", "-i", str(path)])
            _debug(f"screencapture rc={result.returncode}, file_exists={path.exists()}")
            if result.returncode != 0:
                return None
            if path.exists() and path.stat().st_size > 0:
                return True
            return None  # exit 0 but no file = cancelled
        _debug("path: mss (no screencapture)")
        return _capture_mss(path, monitor=monitor)

    # Windows and unknown — try mss
    _debug(f"path: mss (platform={platform})")
    return _capture_mss(path, monitor=monitor)


def _capture_mss(
    filepath: Path,
    region: dict[str, int] | None = None,
    monitor: int | None = None,
) -> bool:
    """Capture with mss.  *region* takes priority, then *monitor*, then primary."""
    try:
        import mss  # type: ignore[import-untyped]
        import mss.tools
        with mss.mss() as sct:
            if region is not None:
                target = region
                _debug(f"mss: capturing custom region {target}")
            elif monitor is not None and 0 < monitor < len(sct.monitors):
                target = sct.monitors[monitor]
                _debug(f"mss: capturing monitor {monitor}: {target}")
            else:
                target = sct.monitors[1]  # primary
                _debug(f"mss: capturing primary monitor: {target}")
            screenshot = sct.grab(target)
            _debug(f"mss: grabbed {screenshot.size}, rgb bytes={len(screenshot.rgb)}")
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filepath))
        exists = filepath.exists()
        size = filepath.stat().st_size if exists else 0
        _debug(f"mss: output file exists={exists}, size={size}")
        return exists and size > 0
    except Exception as e:
        _debug(f"mss: EXCEPTION {type(e).__name__}: {e}")
        return False
