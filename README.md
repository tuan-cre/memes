# Meme Collection

Cross-platform meme manager — CLI, screen capture, clipboard, browser extension, and multi-device sharing.

```bash
pip install git+https://github.com/tuan-cre/memes.git
```

---

## Commands

| Command | What it does |
|---------|-------------|
| `meme list` | List all memes |
| `meme pick` | Interactive browser with fzf + image previews |
| `meme capture` | Select a screen region → save to collection |
| `meme from-clip` | Save clipboard image to collection |
| `meme rename <file>` | Rename a meme |
| `meme trash <file>` | Soft-delete (moves to `.trash/`) |
| `meme serve` | Start HTTP server for sharing |

---

## Install

### From GitHub (any platform)

```bash
pip install git+https://github.com/tuan-cre/memes.git
```

Or to install with optional extras:

```bash
pip install "meme-collection[capture,notify] @ git+https://github.com/tuan-cre/memes.git"
```

### Bootstrap script

```bash
python3 install.py
```

### Manual

Only hard dependency is **Pillow**. Optional deps:

- `mss` — cross-platform screen capture (no native tools needed)
- `plyer` — desktop notifications on all platforms
- `fzf` — interactive picking with fuzzy search
- `chafa` — image previews inside fzf
- `rich` — pretty table formatting

---

## Usage

### Local collection

Save memes to `~/.local/share/memes/`:

```bash
meme capture          # Click and drag to select screen region
meme from-clip        # Save whatever image is in your clipboard
meme list             # See all your memes
meme pick             # Browse with fzf, copy selected to clipboard
meme rename funny     # Rename a meme interactively
meme trash old        # Move to .trash/
```

### Multi-device sharing

Start the server on a machine both you and your friend can reach:

```bash
meme serve --port 9876 --dir /srv/memes
```

On each client machine, create `~/.config/meme/config.json`:

```json
{ "server_url": "http://your-server-ip:9876" }
```

Now all commands work against the shared collection:

```bash
meme list              # Shows memes on the server
meme pick              # Browse and download from server
meme capture           # Saves locally + uploads to server
```

Seed your existing local collection to the server:

```bash
meme serve --seed http://your-server-ip:9876
```

If the server is unreachable, all commands gracefully fall back to local mode.

### Systemd service (Linux)

```ini
[Unit]
Description=Meme Collection Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/meme serve --port 9876 --dir /srv/memes
Restart=always
User=your-username

[Install]
WantedBy=multi-user.target
```

---

## Browser Extension

The `meme-browser/` directory contains a browser extension that saves images directly to your collection via right-click.

### Setup

```bash
./setup-browser.sh
```

Then load the extension from `meme-browser/`:
- **Chrome/Chromium:** `chrome://extensions` → Developer mode → Load unpacked
- **Firefox:** `about:debugging#/runtime/this-firefox` → Load Temporary Add-on

Right-click any image → **Save to Meme Collection** → saved to `~/.local/share/memes/` and copied to clipboard.

---

## Platform Support

| Feature | Linux | macOS | Windows |
|---------|-------|-------|---------|
| Screen capture | slurp+grim or mss | screencapture or mss | mss |
| Clipboard | wl-copy/xclip | osascript / PIL | PIL / win32clipboard |
| Notifications | notify-send / plyer | osascript / plyer | plyer |
| fzf picker | ✓ | ✓ | (via WSL) |
| Server | ✓ | ✓ | ✓ |

---

## Project Structure

```
├── meme.py              # Single-file Python CLI (all commands)
├── server.py            # HTTP sharing server (stdlib only)
├── pyproject.toml       # pip package config
├── install.py           # Bootstrap installer
├── setup-browser.sh     # Browser extension setup
├── meme-browser/        # Chrome/FF browser extension
│   ├── manifest.json
│   ├── background.js
│   └── icons/
├── meme-pick            # Shell wrappers (call meme <subcommand>)
├── meme-list
├── meme-capture
├── ...
└── README.md
```

---

## License

MIT
