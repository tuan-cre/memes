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
import struct
import subprocess
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image

# ─── Constants ───────────────────────────────────────────────────────────────

MEME_DIR = Path.home() / ".local/share/memes"
TRASH_DIR = MEME_DIR / ".trash"


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
    try:
        subprocess.run([name, "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


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


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_list() -> int:
    """List all memes."""
    memes = _list_memes()
    if not memes:
        print("No memes yet! Use capture or from-clip to add some.")
        return 0

    # Try rich for pretty output
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
    """Tab-separated output for fzf input (tab: display\\tfilename)."""
    for m in _list_memes():
        print(f"{m['display']}\t{m['filename']}")
    return 0


def cmd_pick() -> int:
    """Interactive meme browser via fzf."""
    if not _tool_available("fzf"):
        print("Error: fzf is required (install via your package manager)", file=sys.stderr)
        return 1

    memes = _list_memes()
    if not memes:
        _notify("Meme Collection", "No memes yet!")
        return 0

    # Build fzf input
    input_lines = "\n".join(f"{m['display']}\t{m['filename']}" for m in memes)

    # Build preview command
    if _tool_available("chafa"):
        preview = (
            "chafa --symbols=block --fill=block --scale max --align=mid,mid "
            "--size=${FZF_PREVIEW_COLUMNS}x$(( ${FZF_PREVIEW_LINES} - 2 )) "
            f"'{MEME_DIR}/" "{2}'"
        )
    else:
        preview = f"cd '{MEME_DIR}' && echo {{2}} && file {{2}} && echo && stat --printf='Size: %s\\n' {{2}} 2>/dev/null || stat -f 'Size: %z' {{2}} 2>/dev/null; echo; echo 'Install chafa for image previews (brew install chafa)'"

    color = (
        "bg:#050508,bg+:#282838,fg:#d8d8d8,fg+:#ffffff,"
        "hl:#b48ead,hl+:#c7a0c8,pointer:#c7a0c8,info:#5c5c6e,"
        "spinner:#5c5c6e,header:#b48ead,prompt:#b48ead,"
        "border:#5c5c6e,marker:#c7a0c8"
    )

    # Path to self for binds (use absolute, resolve symlinks)
    self_path = Path(sys.argv[0]).resolve()

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
        return 0  # User cancelled

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


def cmd_capture() -> int:
    """Capture a screen region and save to collection."""
    MEME_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    filepath = MEME_DIR / f"meme_{timestamp}.png"
    platform = _platform()

    if platform == "linux":
        try:
            region = subprocess.run(
                ["slurp"], capture_output=True, text=True, check=True
            )
            with filepath.open("wb") as f:
                subprocess.run(["grim", "-g", region.stdout.strip()], stdout=f, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            if not _capture_mss(filepath):
                print("Install slurp+grim or: pip install mss", file=sys.stderr)
                return 1

    elif platform == "macos":
        try:
            subprocess.run(["screencapture", "-i", str(filepath)], check=True)
            if not filepath.exists():
                _notify("Meme Collection", "Capture cancelled")
                return 0
        except FileNotFoundError:
            if not _capture_mss(filepath):
                print("Install screencapture or: pip install mss", file=sys.stderr)
                return 1

    elif platform == "windows":
        if not _capture_mss(filepath):
            print("pip install mss for screen capture on Windows", file=sys.stderr)
            return 1
    else:
        if not _capture_mss(filepath):
            print(f"Unsupported platform: {platform}", file=sys.stderr)
            return 1

    _copy_image(filepath)
    _notify("Meme Collection", f"Captured: {filepath.name}", icon=filepath)
    return 0


def _capture_mss(filepath: Path) -> bool:
    try:
        import mss  # type: ignore[import-untyped]
        with mss.mss() as sct:
            sct.shot(output=str(filepath))
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
    """Rename a meme interactively."""
    filepath = _resolve_path(name)
    if not filepath.exists():
        _notify("Meme Collection", f"File not found: {filepath.name}")
        return 1

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
    new_path = filepath.with_name(f"{raw}.png")

    if new_path.exists():
        print(f"Error: {new_path.name} already exists", file=sys.stderr)
        return 1

    filepath.rename(new_path)
    _notify("Meme Collection", f"Renamed → {new_path.name}", icon=new_path)
    return 0


def cmd_trash(name: str) -> int:
    """Move a meme to .trash/."""
    filepath = _resolve_path(name)
    if not filepath.exists():
        _notify("Meme Collection", f"File not found: {filepath.name}")
        return 1

    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    dest = TRASH_DIR / filepath.name
    filepath.rename(dest)
    _notify("Meme Collection", f"Trashed: {filepath.name}")
    return 0


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
    sub.add_parser("capture", help="Capture screen region")
    sub.add_parser("from-clip", help="Save clipboard image")

    rn = sub.add_parser("rename", help="Rename a meme")
    rn.add_argument("file", help="Filename to rename")

    tr = sub.add_parser("trash", help="Move meme to .trash/")
    tr.add_argument("file", help="Filename to trash")

    sub.add_parser("native-host", help="Native messaging host (browser extension)")
    sub.add_parser("_list-tsv", help=argparse.SUPPRESS)

    return p


def _run(args: argparse.Namespace) -> int:
    dispatch: dict[str, Callable[..., int]] = {
        "list": cmd_list,
        "_list-tsv": cmd_list_tsv,
        "pick": cmd_pick,
        "capture": cmd_capture,
        "from-clip": cmd_from_clip,
        "rename": lambda: cmd_rename(args.file),
        "trash": lambda: cmd_trash(args.file),
        "native-host": cmd_native_host,
    }
    handler = dispatch.get(args.command)
    if handler:
        return handler()
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    main()
