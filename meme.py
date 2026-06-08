#!/usr/bin/env python3
"""
Meme Collection — cross-platform CLI.

Usage:
    meme list              List all memes
    meme pick              Interactive browser (requires fzf + chafa)
    meme capture           Capture screen region to collection
    meme from-clip         Save clipboard image to collection
    meme rename <file>     Rename a meme
    meme trash <file>      Soft-delete a meme
    meme native-host       Native messaging mode (browser extension)

Legacy names work too: meme-pick, meme-capture, etc.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image

# ─── Constants ───────────────────────────────────────────────────────────────

MEME_DIR = Path.home() / ".local/share/memes"
TRASH_DIR = MEME_DIR / ".trash"
CONFIG_DIR = Path.home() / ".config/memes"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Server offline flag — suppresses repeated "server unreachable" messages
_SERVER_OK = True

# Debug mode — set via --debug flag on supported commands
_DEBUG = False


# ─── Platform helpers ────────────────────────────────────────────────────────

def _platform() -> str:
    if sys.platform == "linux":
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return sys.platform


def _tool_available(name: str) -> bool:
    """Check if an executable exists on PATH (no Wayland-display needed)."""
    return shutil.which(name) is not None


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

    print(f"[{title}] {message}", file=sys.stderr)


def _debug(msg: str) -> None:
    """Print debug message to stderr when --debug is enabled."""
    if _DEBUG:
        print(f"[debug] {msg}", file=sys.stderr)


def _copy_image(path: Path) -> bool:
    """Copy a PNG image to the system clipboard."""
    platform = _platform()

    if platform == "linux":
        for tool, args in [
            ("wl-copy", ["wl-copy", "--type", "image/png"]),
            ("xclip", ["xclip", "-selection", "clipboard", "-t", "image/png"]),
        ]:
            try:
                with path.open("rb") as f:
                    subprocess.run(args, stdin=f, check=True)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        return False

    if platform == "macos":
        try:
            ascii_path = str(path)
            subprocess.run(
                ["osascript", "-e",
                 f'set the clipboard to (read (POSIX file "{ascii_path}") '
                 f'as «class PNGf»)'],
                check=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return _copy_image_pil(path)

    if platform == "windows":
        return _copy_image_pil(path)

    return False


def _copy_image_pil(path: Path) -> bool:
    """Fallback clipboard copy using Pillow + platform libs."""
    try:
        from PIL import Image as PILImage
        img = PILImage.open(path)
        img.save(BytesIO(), "PNG")  # validates the image
        # On Windows we'd need win32clipboard here
        # On macOS PIL can't set clipboard directly
        return False
    except Exception:
        return False


# ─── Data ────────────────────────────────────────────────────────────────────

def _list_memes() -> list[dict]:
    """Return sorted list of memes with metadata."""
    MEME_DIR.mkdir(parents=True, exist_ok=True)
    memes: list[dict] = []
    for f in sorted(MEME_DIR.iterdir()):
        if f.suffix.lower() != ".png" or not f.is_file():
            continue
        name = f.stem
        display = name
        ts = None
        if name.startswith("meme_") and name[5:].isdigit():
            ts = int(name[5:])
            display = datetime.fromtimestamp(ts).strftime("%b %d %H:%M")
        memes.append({
            "filename": f.name,
            "path": f,
            "name": name,
            "display": display,
            "timestamp": ts,
            "size": f.stat().st_size,
        })
    return memes


def _resolve_path(name: str) -> Path:
    p = Path(name)
    return p if p.is_absolute() else MEME_DIR / p


def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size}{unit}"
        size //= 1024
    return f"{size}GB"


# ─── Remote server config ───────────────────────────────────────────────────

def _load_config() -> dict:
    """Load user config from ~/.config/meme/config.json."""
    default: dict = {
        "server_url": None,
    }
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            default.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return default


def _server_get(path: str) -> object | None:
    """GET /api/{path} from the configured server. Returns parsed JSON or None."""
    return _server_request("GET", path)


def _server_get_file(path: str, save_to: Path) -> bool:
    """GET /api/{path} (raw file) and write to save_to. Returns success."""
    config = _load_config()
    url = config.get("server_url")
    if not url:
        return False

    full_url = f"{url.rstrip('/')}/api/{path.lstrip('/')}"
    try:
        req = urllib.request.Request(full_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            save_to.write_bytes(resp.read())
        _set_server_ok(True)
        return True
    except (urllib.error.URLError, OSError) as e:
        _handle_server_error(e)
        return False


def _server_post_file(path: str, filepath: Path) -> dict | None:
    """POST /api/{path} as multipart upload. Returns response JSON or None."""
    config = _load_config()
    url = config.get("server_url")
    if not url:
        return None

    import email.message
    import uuid

    full_url = f"{url.rstrip('/')}/api/{path.lstrip('/')}"
    boundary = f"----{uuid.uuid4().hex}"
    filename = filepath.name
    data = filepath.read_bytes()

    # Build multipart body manually (stdlib only)
    part_headers = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: image/png\r\n\r\n'
    ).encode()
    part_footer = f'\r\n--{boundary}--\r\n'.encode()

    body = part_headers + data + part_footer

    try:
        req = urllib.request.Request(
            full_url, data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            _set_server_ok(True)
            return result
    except (urllib.error.URLError, OSError) as e:
        _handle_server_error(e)
        return None


def _server_put(path: str) -> dict | None:
    """PUT /api/{path} on the server. Returns response JSON or None."""
    config = _load_config()
    url = config.get("server_url")
    if not url:
        return None

    full_url = f"{url.rstrip('/')}/api/{path.lstrip('/')}"
    return _do_server_request(full_url, "PUT")


def _server_delete(path: str) -> dict | None:
    """DELETE /api/{path} on the server. Returns response JSON or None."""
    config = _load_config()
    url = config.get("server_url")
    if not url:
        return None

    full_url = f"{url.rstrip('/')}/api/{path.lstrip('/')}"
    return _do_server_request(full_url, "DELETE")


def _server_request(method: str, path: str) -> object | None:
    """Generic request to server. Returns parsed JSON or None."""
    config = _load_config()
    url = config.get("server_url")
    if not url:
        return None

    full_url = f"{url.rstrip('/')}/api/{path.lstrip('/')}"
    try:
        req = urllib.request.Request(full_url, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            _set_server_ok(True)
            return data
    except (urllib.error.URLError, OSError) as e:
        _handle_server_error(e)
        return None


def _do_server_request(url: str, method: str, body: bytes | None = None,
                       headers: dict | None = None) -> dict | None:
    """Low-level server request. Returns JSON dict or None."""
    try:
        req = urllib.request.Request(
            url, data=body, method=method,
            headers=headers or {},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result: dict = json.loads(resp.read())
            _set_server_ok(True)
            return result
    except (urllib.error.URLError, OSError) as e:
        _handle_server_error(e)
        return None


def _set_server_ok(ok: bool) -> None:
    global _SERVER_OK
    _SERVER_OK = ok


def _handle_server_error(exc: Exception) -> None:
    global _SERVER_OK
    if _SERVER_OK:
        print(f"[meme] server unreachable ({exc}), using local mode",
              file=sys.stderr)
        _SERVER_OK = False


def _render_meme_table(memes: list[dict]) -> None:
    """Display a list of meme dicts (local or remote) as a table."""
    if not memes:
        print("No memes on server!")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
        console = Console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Date")
        table.add_column("Filename", style="dim")
        table.add_column("Size")
        for m in memes:
            modified = _format_remote_time(m.get("modified"))
            table.add_row(modified, m["filename"],
                          _format_size(m["size"]))
        console.print(table)
    except ImportError:
        print(f"{'Date':<16} {'Filename':<30} {'Size':<8}")
        print("-" * 56)
        for m in memes:
            modified = _format_remote_time(m.get("modified"))
            print(f"{modified:<16} {m['filename']:<30} {_format_size(m['size']):<8}")


def _format_remote_time(ts: float | None) -> str:
    if ts:
        return datetime.fromtimestamp(ts).strftime("%b %d %H:%M")
    return ""


# ─── Native messaging protocol (browser extension) ──────────────────────────

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

        filename = f"meme_{int(time.time())}.png"
        filepath = MEME_DIR / filename
        MEME_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(png_data)

        _copy_image(filepath)
        _notify("Meme Collection", f"Saved: {filename}", icon=filepath)
        return {"success": True, "filename": filename}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _upload_if_remote(filepath: Path) -> None:
    """Upload a file to the server if configured. Non-blocking on failure."""
    config = _load_config()
    if not config.get("server_url"):
        return
    result = _server_post_file("memes", filepath)
    if result is not None:
        print(f"  → uploaded to server as {result.get('filename')}")
    else:
        print("  → upload to server failed (saved locally)", file=sys.stderr)


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_list() -> int:
    """List all memes (local or remote)."""
    # Try remote first if configured
    remote = _server_get("memes")
    if remote is not None:
        memes: list[dict] = list(remote)  # type: ignore[assignment]
        _render_meme_table(memes)
        return 0

    # Fall back to local
    memes = _list_memes()
    if not memes:
        print("No memes yet! Use capture or from-clip to add some.")
        return 0

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Date")
        table.add_column("Filename", style="dim")
        table.add_column("Size")
        for m in memes:
            table.add_row(m["display"], m["filename"], _format_size(m["size"]))
        console.print(table)
    except ImportError:
        print(f"{'Date':<16} {'Filename':<30} {'Size':<8}")
        print("-" * 56)
        for m in memes:
            print(f"{m['display']:<16} {m['filename']:<30} {_format_size(m['size']):<8}")
    return 0


def cmd_list_tsv() -> int:
    """Tab-separated output for fzf input.  Tries server first, falls back to local."""
    remote = _server_get("memes")
    if remote is not None:
        for m in list(remote):
            print(f"{m.get('display', m['filename'])}\t{m['filename']}")
        return 0
    for m in _list_memes():
        print(f"{m['display']}\t{m['filename']}")
    return 0


def cmd_pick() -> int:
    """Interactive meme browser via fzf (local or remote)."""
    if not _tool_available("fzf"):
        print("Error: fzf is required (install via your package manager)", file=sys.stderr)
        return 1

    color = (
        "bg:#050508,bg+:#282838,fg:#d8d8d8,fg+:#ffffff,"
        "hl:#b48ead,hl+:#c7a0c8,pointer:#c7a0c8,info:#5c5c6e,"
        "spinner:#5c5c6e,header:#b48ead,prompt:#b48ead,"
        "border:#5c5c6e,marker:#c7a0c8"
    )
    self_path = Path(sys.argv[0]).resolve()

    # ── Try remote mode ──────────────────────────────────────────────────
    remote_memes = _server_get("memes")
    if remote_memes is not None:
        memes: list[dict] = list(remote_memes)  # type: ignore[assignment]
        if not memes:
            _notify("Meme Collection", "No memes on server!")
            return 0

        input_lines = "\n".join(
            f"{m.get('display', m['filename'])}\t{m['filename']}"
            for m in memes
        )
        server_url = _load_config()['server_url'].rstrip('/')

        if _tool_available("chafa"):
            preview = (
                "mkdir -p /tmp/meme-cache; "
                f"cache='/tmp/meme-cache/{{2}}'; "
                f"[ -f \"$cache\" ] || curl -s -o \"$cache\" "
                f"'{server_url}/api/memes/'{{2}}; "
                f"chafa --symbols=block --fill=block --scale max --align=mid,mid "
                f"--size=${{FZF_PREVIEW_COLUMNS}}x$(( ${{FZF_PREVIEW_LINES}} - 2 )) "
                f"\"$cache\" 2>/dev/null; "
                f"echo '  {{2}}'"
            )
        else:
            preview = (
                f"echo '  {{2}}' && echo && echo 'Select to download and open'"
            )

        fzf = subprocess.Popen(
            [
                "fzf",
                "--delimiter", "\t",
                "--with-nth", "1",
                "--preview", preview,
                "--preview-window", "right:60%:border-rounded",
                "--layout=reverse",
                "--border=rounded",
                "--header", "  MEME COLLECTION (SERVER)  ",
                "--prompt", "▸ ",
                "--color", color,
                "--height=100%",
                "--no-info",
                "--bind", f"ctrl-p:execute(imv '/tmp/meme-cache/" "{2}' 2>/dev/null)+abort",
                "--bind", f"ctrl-d:execute({self_path} trash " "{2})+reload("
                          f"{self_path} _list-tsv)",
                "--bind", f"ctrl-r:execute({self_path} rename " "{2})+reload("
                          f"{self_path} _list-tsv)",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        result, _ = fzf.communicate(input=input_lines)

        if fzf.returncode != 0 or not result.strip():
            return 0

        filename = result.strip().split("\t")[-1]
        # Download to temp and copy to clipboard
        tmp = Path(tempfile.mkstemp(suffix=".png")[1])
        if not _server_get_file(f"memes/{filename}", tmp):
            print(f"Error: could not download {filename}", file=sys.stderr)
            return 1

        # Open with image viewer
        for viewer in ("imv", "feh", "sxiv", "xdg-open"):
            if _tool_available(viewer):
                subprocess.Popen([viewer, str(tmp)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break

        # Copy to clipboard
        if _copy_image(tmp):
            _notify("Meme Collection", f"Copied from server: {filename}", icon=tmp)
        else:
            print(f"Downloaded: {tmp}")
        return 0

    # ── Local mode ───────────────────────────────────────────────────────
    memes = _list_memes()
    if not memes:
        _notify("Meme Collection", "No memes yet!")
        return 0

    input_lines = "\n".join(f"{m['display']}\t{m['filename']}" for m in memes)

    if _tool_available("chafa"):
        preview = (
            "chafa --symbols=block --fill=block --scale max --align=mid,mid "
            "--size=${FZF_PREVIEW_COLUMNS}x$(( ${FZF_PREVIEW_LINES} - 2 )) "
            f"'{MEME_DIR}/" "{2}'"
        )
    else:
        preview = (f"cd '{MEME_DIR}' && echo {{2}} && file {{2}} && echo && "
                   "stat --printf='Size: %s\\n' {{2}} 2>/dev/null || "
                   "stat -f 'Size: %z' {{2}} 2>/dev/null; echo; echo "
                   "'Install chafa for image previews (brew install chafa)'")

    fzf = subprocess.Popen(
        [
            "fzf",
            "--delimiter", "\t",
            "--with-nth", "1",
            "--preview", preview,
            "--preview-window", "right:80%:border-rounded:wrap",
            "--layout=reverse",
            "--border=rounded",
            "--header", "  MEME COLLECTION  ",
            "--prompt", "▸ ",
            "--color", color,
            "--height=100%",
            "--no-info",
            "--bind", f"ctrl-p:execute(imv '{MEME_DIR}/" "{2}' 2>/dev/null)+abort",
            "--bind", f"ctrl-d:execute({self_path} trash " "{2})+reload("
                      f"{self_path} _list-tsv)",
            "--bind", f"ctrl-r:execute({self_path} rename " "{2})+reload("
                      f"{self_path} _list-tsv)",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    result, _ = fzf.communicate(input=input_lines)

    if fzf.returncode != 0 or not result.strip():
        return 0

    selected = result.strip()
    filename = selected.split("\t")[-1]
    display = selected.split("\t")[0]
    filepath = MEME_DIR / filename

    if not filepath.exists():
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        return 1

    if _copy_image(filepath):
        _notify("Meme Collection", f"Copied: {display}", icon=filepath)
    else:
        print(f"Saved at: {filepath}")
    return 0


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
                    # Parse comma-separated byte values
                    raw = bytes(int(b) for b in result.stdout.strip().split(", "))
                    filepath.write_bytes(raw)
                    saved = True
            except Exception:
                pass

    elif platform == "windows":
        saved = _clipboard_image_pil(filepath)

    if not saved or not filepath.exists() or filepath.stat().st_size == 0:
        filepath.unlink(missing_ok=True)
        _notify("Meme Collection", "Clipboard doesn't contain an image")
        return 1

    _notify("Meme Collection", f"Saved: {filepath.name}", icon=filepath)

    # Upload to server if configured
    _upload_if_remote(filepath)

    return 0


def _clipboard_image_pil(filepath: Path) -> bool:
    """Read clipboard image via PIL and save."""
    try:
        from PIL import ImageGrab  # type: ignore[import-untyped]
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            img.save(filepath, "PNG")
            return True
    except Exception:
        pass
    return False


def cmd_rename(name: str) -> int:
    """Rename a meme interactively (local + server if configured)."""
    filepath = _resolve_path(name)

    try:
        raw = input("New name: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        _notify("Meme Collection", "Rename cancelled")
        return 0

    if not raw:
        _notify("Meme Collection", "Rename cancelled")
        return 0

    raw = raw.replace("/", "_").replace(" ", "_")

    # Rename on server if configured (works even if file not local)
    server_result = _server_put(f"memes/{name}:{raw}.png")
    if server_result is not None:
        _notify("Meme Collection", f"Renamed on server → {raw}.png")
        return 0

    # Fall back to local rename
    if not filepath.exists():
        _notify("Meme Collection", f"File not found: {filepath.name}")
        return 1

    new_path = filepath.with_name(f"{raw}.png")
    if new_path.exists():
        print(f"Error: {new_path.name} already exists", file=sys.stderr)
        return 1

    filepath.rename(new_path)
    _notify("Meme Collection", f"Renamed → {new_path.name}", icon=new_path)
    return 0


def cmd_trash(name: str) -> int:
    """Move a meme to .trash/ (local + server if configured)."""
    filepath = _resolve_path(name)

    # Delete on server if configured (works even if file not local)
    server_result = _server_delete(f"memes/{name}")
    if server_result is not None:
        # Also trash locally if file exists
        if filepath.exists():
            TRASH_DIR.mkdir(parents=True, exist_ok=True)
            dest = TRASH_DIR / filepath.name
            filepath.rename(dest)
        _notify("Meme Collection", f"Trashed: {name}")
        return 0

    # Fall back to local trash
    if not filepath.exists():
        _notify("Meme Collection", f"File not found: {filepath.name}")
        return 1

    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    dest = TRASH_DIR / filepath.name
    filepath.rename(dest)
    _notify("Meme Collection", f"Trashed: {filepath.name}")
    return 0


def cmd_serve(port: int = 9876, memes_dir: str | None = None,
              seed_url: str | None = None) -> int:
    """Start the meme sharing server or seed memes to an existing one."""
    if seed_url:
        # Seed mode: upload local memes to an existing server
        from server import seed as _seed
        _seed(seed_url, memes_dir or str(MEME_DIR))
        return 0

    from server import serve as _serve
    _serve(port, memes_dir or str(MEME_DIR))
    return 0


def cmd_picker() -> int:
    """Open a terminal window running ``meme pick`` (cross-platform)."""
    try:
        import picker  # type: ignore[import-untyped]  # noqa: F100
        return picker.run()
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_native_host() -> int:
    """Native messaging host for browser extension (stdin/stdout protocol)."""
    MEME_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        message = _read_native_msg()
        if not message:
            break

        action = message.get("action", "")
        if action == "save":
            _send_native_msg(_save_native_image(message.get("data", "")))
        elif action == "ping":
            _send_native_msg({"success": True, "pong": True})
        else:
            _send_native_msg({"success": False,
                              "error": f"Unknown action: {action}"})
    return 0




# ─── CLI dispatch ────────────────────────────────────────────────────────────

def main() -> None:
    argv = sys.argv[1:]
    prog = Path(sys.argv[0]).stem  # e.g. "meme", "meme-pick", "meme-capture"

    # Legacy name → command mapping (so symlinks/wrappers still work)
    legacy: dict[str, str] = {
        "meme-pick": "pick",
        "meme-list": "list",
        "meme-capture": "capture",
        "meme-from-clip": "from-clip",
        "meme-rename": "rename",
        "meme-trash": "trash",
        "meme-native-host": "native-host",
        "meme-picker": "picker",
    }

    if prog in legacy:
        # Called as e.g. "meme-pick" — insert the subcommand
        argv = [legacy[prog]] + ([" ".join(argv)] if prog in ("rename", "trash") else argv)

    parser = _build_parser()
    args = parser.parse_args(argv)

    exit(_run(args))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="meme", description="Meme Collection CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all memes")
    sub.add_parser("pick", help="Interactive browser (requires fzf + chafa)")
    cp = sub.add_parser("capture", help="Capture screen region")
    cp.add_argument("-m", "--monitor", type=int, default=None,
                    help="Monitor index to capture (1-indexed, default: primary)")
    cp.add_argument("-d", "--debug", action="store_true",
                    help="Print debug diagnostics to stderr")
    sub.add_parser("from-clip", help="Save clipboard image")

    rn = sub.add_parser("rename", help="Rename a meme")
    rn.add_argument("file", help="Filename to rename")

    tr = sub.add_parser("trash", help="Move meme to .trash/")
    tr.add_argument("file", help="Filename to trash")

    sv = sub.add_parser("serve", help="Start meme sharing server")
    sv.add_argument("--port", type=int, default=9876,
                    help="Port to listen on (default: 9876)")
    sv.add_argument("--dir", default=None,
                    help="Memes directory (default: ~/.local/share/memes)")
    sv.add_argument("--seed", metavar="SERVER_URL",
                    help="Upload local memes to existing server and exit")

    sub.add_parser("picker", help="Open ``meme pick`` in a dedicated terminal window")
    sub.add_parser("native-host", help="Native messaging host (browser extension)")
    sub.add_parser("_list-tsv", help=argparse.SUPPRESS)

    return p


def _run(args: argparse.Namespace) -> int:
    # Enable debug mode before dispatching (so capture logging works)
    if getattr(args, "debug", False):
        global _DEBUG
        _DEBUG = True

    dispatch: dict[str, Callable[..., int]] = {
        "list": cmd_list,
        "_list-tsv": cmd_list_tsv,
        "pick": cmd_pick,
        "capture": lambda: cmd_capture(monitor=args.monitor),
        "from-clip": cmd_from_clip,
        "rename": lambda: cmd_rename(args.file),
        "trash": lambda: cmd_trash(args.file),
        "serve": lambda: cmd_serve(args.port, args.dir, args.seed),
        "native-host": cmd_native_host,
    "picker": cmd_picker,
}
    handler = dispatch.get(args.command)
    if handler:
        return handler()
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    main()
