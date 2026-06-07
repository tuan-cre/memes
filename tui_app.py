#!/usr/bin/env python3
"""
Meme Collection TUI — Textual-based terminal UI for browsing memes.

Usage:
    meme tui

Requires: textual (pip), chafa (system package)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Input, Label, RichLog

# Import shared logic from the meme module
from meme import (
    MEME_DIR,
    _list_memes,
    _copy_image,
    _notify,
    _load_config,
    _server_get,
    _server_get_file,
    _format_size,
)


def _chafa(path: Path, width: int, height: int) -> str:
    """Run chafa on *path* and return ANSI output."""
    if not shutil.which("chafa"):
        return "[dim]Install chafa for image previews[/dim]"
    try:
        r = subprocess.run(
            [
                "chafa",
                "--symbols=block",
                "--fill=block",
                "--scale=max",
                "--align=mid,mid",
                f"--size={width}x{height}",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
        return f"[dim]No preview[/dim]"
    except Exception as e:
        return f"[red]Preview error: {e}[/red]"


class MemeTUI(App):
    """Textual-based terminal UI for browsing the meme collection."""

    CSS = """
    Screen {
        background: #0e0e12;
    }

    #main-container {
        height: 100%;
    }

    #left-panel {
        width: 40%;
        min-width: 30;
        border-right: solid #282838;
    }

    #right-panel {
        width: 60%;
    }

    #search {
        dock: top;
        margin: 0 1;
    }

    DataTable {
        height: 1fr;
    }

    #preview {
        height: 1fr;
        padding: 1 1;
    }

    #status-label {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: #1a1a2e;
        color: #5c5c6e;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("slash", "focus_search", "Search", show=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=True),
        Binding("up", "cursor_up", "Up", show=True),
        Binding("enter", "copy", "Copy", show=True),
        Binding("d", "trash", "Trash", show=True),
        Binding("r", "rename", "Rename", show=True),
        Binding("c", "capture", "Capture", show=True),
        Binding("g", "first_row", "Top", show=False),
        Binding("G", "last_row", "Bottom", show=False),
        Binding("escape", "quit", "Quit", show=False),
    ]

    memes: list[dict] = []
    filtered_memes: list[dict] = []
    current_filename: str | None = None
    is_server: bool = False
    server_url: str | None = None

    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield Input(id="search", placeholder="Search memes...")
                yield DataTable(id="meme-table", cursor_type="row")
                yield Label(id="status-label")
            with Vertical(id="right-panel"):
                yield RichLog(id="preview", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        """Set up the UI after mount."""
        table = self.query_one("#meme-table", DataTable)
        table.add_columns("Name", "Date", "Size")

        config = _load_config()
        self.server_url = config.get("server_url")
        self.is_server = self.server_url is not None

        self._load_memes()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_memes(self) -> None:
        """Fetch memes from local dir or server and populate the table."""
        table = self.query_one("#meme-table", DataTable)
        table.clear()

        self.memes.clear()

        if self.is_server:
            remote = _server_get("memes")
            if remote is not None:
                for m in remote:
                    self.memes.append(m)
                for m in self.memes:
                    table.add_row(
                        m.get("display", m["filename"]),
                        "",
                        "",
                        key=m["filename"],
                    )
        else:
            self.memes = _list_memes()
            for m in self.memes:
                table.add_row(
                    m["display"],
                    (
                        datetime.fromtimestamp(m["timestamp"]).strftime("%b %d %H:%M")
                        if m["timestamp"]
                        else ""
                    ),
                    _format_size(m["size"]),
                    key=m["filename"],
                )

        self.filtered_memes = list(self.memes)
        self._update_status()

    def _update_status(self) -> None:
        label = self.query_one("#status-label", Label)
        n = len(self.memes)
        if self.is_server:
            label.update(f"  [{n} meme{'s' if n != 1 else ''} on server]")
        else:
            label.update(f"  [{n} meme{'s' if n != 1 else ''}]")

    # ------------------------------------------------------------------
    # Search / filter
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the table as the user types in the search input."""
        if event.input.id != "search":
            return
        query = event.value.lower()
        table = self.query_one("#meme-table", DataTable)
        table.clear()
        for m in self.memes:
            name = m["filename"].lower()
            display = m.get("display", "").lower()
            if query in name or query in display:
                table.add_row(
                    m["display"],
                    (
                        datetime.fromtimestamp(m["timestamp"]).strftime("%b %d %H:%M")
                        if m.get("timestamp")
                        else ""
                    ),
                    _format_size(m["size"]) if not self.is_server else "",
                    key=m["filename"],
                )

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _get_meme_path(self, filename: str) -> Path | None:
        """Return a local path for *filename*, downloading from server if needed."""
        if self.is_server:
            cache = Path(tempfile.gettempdir()) / "meme-cache"
            cache.mkdir(exist_ok=True)
            p = cache / filename
            if not p.exists():
                if not _server_get_file(f"memes/{filename}", p):
                    return None
            return p
        p = MEME_DIR / filename
        return p if p.exists() else None

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """Show preview when the cursor lands on a row."""
        filename = str(event.row_key.value)
        self.current_filename = filename
        self._render_preview(filename)

    @work(thread=True, exit_on_error=False)
    async def _render_preview(self, filename: str) -> None:
        """Run chafa in a thread and show output in the preview panel."""
        preview = self.query_one("#preview", RichLog)

        mpath = self._get_meme_path(filename)
        if mpath is None:
            preview.clear()
            preview.write("[red]File not found[/red]")
            return

        try:
            w = preview.size.width - 2
            h = preview.size.height - 2
        except Exception:
            w, h = 40, 20

        output = _chafa(mpath, max(w, 10), max(h, 5))
        preview.clear()
        preview.write(output)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_cursor_down(self) -> None:
        table = self.query_one("#meme-table", DataTable)
        try:
            table.action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        table = self.query_one("#meme-table", DataTable)
        try:
            table.action_cursor_up()
        except Exception:
            pass

    def action_first_row(self) -> None:
        table = self.query_one("#meme-table", DataTable)
        try:
            table.move_cursor(row=0)
        except Exception:
            pass

    def action_last_row(self) -> None:
        table = self.query_one("#meme-table", DataTable)
        try:
            table.move_cursor(row=table.row_count - 1)
        except Exception:
            pass

    def action_copy(self) -> None:
        """Copy the highlighted meme to the clipboard (or download + copy)."""
        fname = self.current_filename
        if not fname:
            return
        mpath = self._get_meme_path(fname)
        if mpath is None:
            self._notify_status(f"File not found: {fname}")
            return

        if not self.is_server:
            if _copy_image(mpath):
                _notify("Meme Collection", f"Copied: {fname}", icon=mpath)
            else:
                self._notify_status(f"Saved: {mpath}")
        else:
            if _copy_image(mpath):
                _notify("Meme Collection", f"Copied from server: {fname}", icon=mpath)
            else:
                self._notify_status(f"Downloaded: {mpath}")

    def action_trash(self) -> None:
        """Move highlighted meme to .trash/."""
        fname = self.current_filename
        if not fname:
            return

        if self.is_server:
            from meme import _server_delete

            if _server_delete(f"memes/{fname}") is not None:
                _notify("Meme Collection", f"Trashed from server: {fname}")
                self._load_memes()
            else:
                self._notify_status("Failed to trash on server")
            return

        src = MEME_DIR / fname
        if not src.exists():
            self._notify_status(f"Not found: {fname}")
            return
        trash = MEME_DIR / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        dest = trash / fname
        # Avoid name collision
        if dest.exists():
            stem, ext = fname.rsplit(".", 1) if "." in fname else (fname, "png")
            dest = trash / f"{stem}_{int(datetime.now().timestamp())}.{ext}"
        src.rename(dest)
        _notify("Meme Collection", f"Trashed: {fname}")
        self._load_memes()

    def action_rename(self) -> None:
        """Rename highlighted meme (push new name via Input)."""
        fname = self.current_filename
        if not fname or self.is_server:
            self._notify_status("Rename not supported in server mode")
            return

        # Focus search input and pre-fill with current name for editing
        inp = self.query_one("#search", Input)
        # Strip .png extension
        base = fname.rsplit(".", 1)[0] if fname.endswith(".png") else fname
        inp.value = f"rename:{base}"
        inp.focus()

    def action_capture(self) -> None:
        """Launch a capture and reload."""
        from meme import cmd_capture

        self._notify_status("Launching capture…")
        # Capture runs in a subprocess — tricky from the TUI.
        # For now just notify.
        _notify("Meme Collection", "Run 'meme capture' in another terminal")

    def _notify_status(self, msg: str) -> None:
        label = self.query_one("#status-label", Label)
        old = label.renderable or ""
        label.update(f"  {msg}")
        self.set_timer(3, lambda: label.update(old))


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------

def run() -> int:
    """Launch the TUI. Called from ``meme tui``."""
    app = MemeTUI()
    exit_code = app.run()
    return exit_code if exit_code is not None else 0


if __name__ == "__main__":
    sys.exit(run())
