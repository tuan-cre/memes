#!/usr/bin/env python3
"""
Meme Collection — HTTP server for sharing memes across devices.

Usage:
    python server.py [--port PORT] [--dir MEMES_DIR]

Endpoints:
    GET    /api/memes              List all memes (JSON)
    GET    /api/memes/<name>       Download a meme (PNG)
    POST   /api/memes              Upload a meme (multipart/form-data)
    PUT    /api/memes/<old>:<new>  Rename a meme
    DELETE /api/memes/<name>       Soft-delete a meme (→ .trash/)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path


MEMES_DIR: Path = Path("./memes")
TRASH_DIR: Path = MEMES_DIR / ".trash"
PORT: int = 9876


class MemeHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the meme API."""

    # ── helpers ──────────────────────────────────────────────────────────────

    def _send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        stat = path.stat()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Disposition",
                         f'inline; filename="{path.name}"')
        self._cors()
        self.send_header("Content-Length", str(stat.st_size))
        self.end_headers()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                self.wfile.write(chunk)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")

    def _parse_path(self) -> tuple[str, str]:
        """Return (endpoint, *args) from the request path.
        
        Examples:
            /api/memes         → ("memes", "")
            /api/memes/foo.png → ("memes", "foo.png")
            /api/memes/a:b     → ("memes", "a:b")
        """
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path.startswith("/api/"):
            rest = path[5:]  # strip "/api/"
            if "/" in rest:
                endpoint, arg = rest.split("/", 1)
                return endpoint, arg
            return rest, ""
        return "", ""

    def _list_memes(self) -> list[dict]:
        MEMES_DIR.mkdir(parents=True, exist_ok=True)
        memes: list[dict] = []
        for f in sorted(MEMES_DIR.iterdir(),
                        key=lambda p: p.stat().st_mtime, reverse=True):
            if f.suffix.lower() == ".png" and f.is_file():
                name = f.stem
                display = name
                ts = None
                if name.startswith("meme_") and name[5:].isdigit():
                    ts = int(name[5:])
                    display = datetime.fromtimestamp(ts).strftime("%b %d %H:%M")
                memes.append({
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                    "display": display,
                })
        return memes

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[meme-server] {args[0]} {args[1]} {args[2]}", file=sys.stderr)

    # ── HTTP methods ─────────────────────────────────────────────────────────

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        endpoint, arg = self._parse_path()
        if endpoint == "memes" and not arg:
            self._send_json(self._list_memes())
        elif endpoint == "memes" and arg:
            filepath = MEMES_DIR / arg
            if filepath.exists() and filepath.is_file():
                self._send_file(filepath)
            else:
                self._send_json({"error": "not found"}, 404)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        endpoint, arg = self._parse_path()
        if endpoint == "memes" and not arg:
            self._handle_upload()
        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_upload(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))

        if "multipart/form-data" in content_type:
            self._handle_multipart_upload()
        elif content_type == "application/json":
            self._handle_json_upload(content_length)
        else:
            self._send_json({"error": "unsupported Content-Type"}, 400)

    def _handle_multipart_upload(self) -> None:
        """Parse multipart form and save the uploaded file."""
        content_type = self.headers.get("Content-Type", "")
        boundary = content_type.split("boundary=", 1)[-1].strip()
        if not boundary:
            self._send_json({"error": "no boundary in Content-Type"}, 400)
            return

        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        filename = f"meme_{int(time.time())}.png"
        data: bytes | None = None

        # Simple multipart parser (stdlib-only, no cgi.FieldStorage)
        for part in raw.split(b"--" + boundary.encode()):
            if b"Content-Disposition" not in part:
                continue
            # Extract filename if provided
            for line in part.split(b"\r\n"):
                if b'filename="' in line.lower():
                    fn = line.split(b'filename="', 1)[-1].split(b'"', 1)[0]
                    if fn:
                        filename = fn.decode("utf-8", errors="replace")
                    break
            # Find the blank line separating headers from body
            if b"\r\n\r\n" in part:
                data = part.split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n--")

        if data is None:
            self._send_json({"error": "no file data found"}, 400)
            return

        MEMES_DIR.mkdir(parents=True, exist_ok=True)
        filepath = MEMES_DIR / filename
        # Avoid overwriting — append timestamp if exists
        stem, suffix = filepath.stem, filepath.suffix
        counter = 1
        while filepath.exists():
            filepath = MEMES_DIR / f"{stem}_{counter}{suffix}"
            counter += 1
        filepath.write_bytes(data)
        self._send_json({"filename": filepath.name, "size": len(data)}, 201)

    def _handle_json_upload(self, length: int) -> None:
        """Handle JSON body with data_b64 field (for seed/scripting)."""
        body = json.loads(self.rfile.read(length).decode())
        data_b64 = body.get("data_b64", "")
        filename = body.get("filename", f"meme_{int(time.time())}.png")
        import base64
        data = base64.b64decode(data_b64)

        MEMES_DIR.mkdir(parents=True, exist_ok=True)
        filepath = MEMES_DIR / filename
        filepath.write_bytes(data)
        self._send_json({"filename": filepath.name, "size": len(data)}, 201)

    def do_PUT(self) -> None:  # noqa: N802
        endpoint, arg = self._parse_path()
        if endpoint == "memes" and arg and ":" in arg:
            old_name, new_name = arg.split(":", 1)
            old_path = MEMES_DIR / old_name
            new_path = MEMES_DIR / new_name
            if not old_path.exists():
                self._send_json({"error": "not found"}, 404)
            elif new_path.exists():
                self._send_json({"error": "already exists"}, 409)
            else:
                old_path.rename(new_path)
                self._send_json({"ok": True, "filename": new_name})
        else:
            self._send_json({"error": "invalid request"}, 400)

    def do_DELETE(self) -> None:  # noqa: N802
        endpoint, arg = self._parse_path()
        if endpoint == "memes" and arg:
            filepath = MEMES_DIR / arg
            if not filepath.exists():
                self._send_json({"error": "not found"}, 404)
            else:
                TRASH_DIR.mkdir(parents=True, exist_ok=True)
                dest = TRASH_DIR / filepath.name
                counter = 1
                while dest.exists():
                    stem = filepath.stem
                    dest = TRASH_DIR / f"{stem}_{counter}{filepath.suffix}"
                    counter += 1
                filepath.rename(dest)
                self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, 404)


# ─── CLI entry point ─────────────────────────────────────────────────────────

def serve(port: int = PORT, memes_dir: str | None = None) -> None:
    """Start the meme server."""
    global MEMES_DIR, TRASH_DIR
    if memes_dir:
        MEMES_DIR = Path(memes_dir).resolve()
        TRASH_DIR = MEMES_DIR / ".trash"
    MEMES_DIR.mkdir(parents=True, exist_ok=True)
    server = HTTPServer(("0.0.0.0", port), MemeHandler)
    print(f"[meme-server] listening on http://0.0.0.0:{port}")
    print(f"[meme-server] memes directory: {MEMES_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[meme-server] shutting down")
        server.server_close()


def seed(server_url: str, memes_dir: str | None = None) -> None:
    """Upload local memes to an existing server."""
    import base64
    import urllib.request

    local_dir = Path(memes_dir) if memes_dir else MEMES_DIR
    if not local_dir.exists():
        print(f"No memes found at {local_dir}")
        return

    memes = sorted(local_dir.iterdir())
    pngs = [f for f in memes if f.suffix.lower() == ".png" and f.is_file()]
    if not pngs:
        print(f"No PNG memes found at {local_dir}")
        return

    url = server_url.rstrip("/") + "/api/memes"
    uploaded = 0
    skipped = 0

    # First, get existing filenames from server
    try:
        req = urllib.request.Request(f"{server_url.rstrip('/')}/api/memes")
        with urllib.request.urlopen(req, timeout=5) as resp:
            existing = {m["filename"] for m in json.loads(resp.read())}
    except Exception as e:
        print(f"Could not connect to server: {e}")
        return

    for fp in pngs:
        if fp.name in existing:
            skipped += 1
            continue
        try:
            data_b64 = base64.b64encode(fp.read_bytes()).decode()
            body = json.dumps({"filename": fp.name, "data_b64": data_b64}).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                print(f"  ✓ {fp.name} → {result['filename']}")
                uploaded += 1
        except Exception as e:
            print(f"  ✗ {fp.name}: {e}")

    print(f"\nUploaded {uploaded}, skipped {skipped} (already on server)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Meme Collection Server")
    parser.add_argument("--port", type=int, default=PORT,
                        help=f"Port to listen on (default: {PORT})")
    parser.add_argument("--dir", default=None,
                        help="Memes directory (default: ./memes)")
    parser.add_argument("--seed", metavar="SERVER_URL",
                        help="Upload local memes to an existing server, then exit")
    args = parser.parse_args()

    if args.seed:
        seed(args.seed, args.dir)
    else:
        serve(args.port, args.dir)


if __name__ == "__main__":
    main()
