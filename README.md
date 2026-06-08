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
| `meme pick` | Interactive browser with fzf + chafa image previews |
| `meme picker` | Open `meme pick` in a dedicated terminal window |
| `meme capture` | Select a screen region → save to collection |
| `meme from-clip` | Save clipboard image to collection |
| `meme rename <file>` | Rename a meme |
| `meme trash <file>` | Soft-delete (moves to `.trash/`) |
| `meme serve` | Start HTTP server for sharing |

---

## Install

### Linux

```bash
# Dependencies: fzf (fuzzy picker) + chafa (image previews)
sudo apt install fzf chafa    # Debian/Ubuntu
sudo pacman -S fzf chafa      # Arch
sudo dnf install fzf chafa    # Fedora

# Install the tool (recommended: pipx for isolated CLI tools)
pipx install git+https://github.com/tuan-cre/memes.git

# Or with pip if you prefer:
# pip install git+https://github.com/tuan-cre/memes.git
```

### Windows 11

```powershell
# Dependencies
winget install fzf
winget install hpjansson.Chafa

# Install the tool
pip install git+https://github.com/tuan-cre/memes.git
```

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

On each client machine, create `~/.config/memes/config.json`:

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
| fzf picker | ✓ | ✓ | ✓ (native via winget) |
| Server | ✓ | ✓ | ✓ |

---

## Project Structure

```
├── meme.py              # Single-file Python CLI (all commands)
├── picker.py            # Terminal wrapper (opens `meme pick` in a new window)
├── server.py            # HTTP sharing server (stdlib only)
├── pyproject.toml       # pip package config
├── install.py           # Bootstrap installer
├── setup-browser.sh     # Browser extension setup
├── meme-browser/        # Chrome/FF browser extension
│   ├── manifest.json
│   ├── background.js
│   └── icons/
└── README.md
```

---

## License

MIT
