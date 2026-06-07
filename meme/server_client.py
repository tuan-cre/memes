"""Server HTTP client — all _server_* functions consolidated."""
from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from io import BytesIO

from meme.config import MEME_DIR, _load_config
from meme.platform import _notify


_SERVER_OK = True


def _server_url(path: str) -> str | None:
    """Build full API URL from config. Returns None if server not configured."""
    url = _load_config().get("server_url")
    if not url:
        return None
    return f"{url.rstrip('/')}/api/{path.lstrip('/')}"


def _set_server_ok(ok: bool) -> None:
    global _SERVER_OK
    _SERVER_OK = ok


def _handle_server_error(exc: Exception) -> None:
    global _SERVER_OK
    if _SERVER_OK:
        print(f"[meme] server unreachable ({exc}), using local mode",
              file=sys.stderr)
        _SERVER_OK = False


# ── High-level helpers ────────────────────────────────────────────────────────


def _server_get(path: str) -> object | None:
    """GET /api/{path}. Returns parsed JSON or None."""
    return _server_request("GET", path)


def _server_get_file(path: str, save_to: Path) -> bool:
    """GET /api/{path} (raw file) and write to save_to."""
    full_url = _server_url(path)
    if not full_url:
        return False
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
    full_url = _server_url(path)
    if not full_url:
        return None

    boundary = f"----{uuid.uuid4().hex}"
    filename = filepath.name
    data = filepath.read_bytes()

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
    """PUT /api/{path}. Returns response JSON or None."""
    full_url = _server_url(path)
    if not full_url:
        return None
    return _do_server_request(full_url, "PUT")


def _server_delete(path: str) -> dict | None:
    """DELETE /api/{path}. Returns response JSON or None."""
    full_url = _server_url(path)
    if not full_url:
        return None
    return _do_server_request(full_url, "DELETE")


def _server_request(method: str, path: str) -> object | None:
    """Generic request to server. Returns parsed JSON or None."""
    full_url = _server_url(path)
    if not full_url:
        return None
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


def _upload_if_remote(filepath: Path) -> None:
    """Upload a file to the server if configured. Non-blocking on failure."""
    if not _load_config().get("server_url"):
        return
    result = _server_post_file("memes", filepath)
    if result is not None:
        print(f"  → uploaded to server as {result.get('filename')}")
    else:
        print("  → upload to server failed (saved locally)", file=sys.stderr)
