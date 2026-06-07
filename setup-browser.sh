#!/bin/bash
# Setup script for Meme Collection browser extension
# Registers the native messaging host and prints loading instructions
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST_SRC="$SCRIPT_DIR/me.memes.collection.json"
HOST_SCRIPT="$SCRIPT_DIR/meme-native-host"
EXTENSION_DIR="$SCRIPT_DIR/meme-browser"

echo "Setting up Meme Collection browser extension..."
echo ""

# Make native host executable
chmod +x "$HOST_SCRIPT"

# Register native messaging host for all known Chromium-based browsers
for nmh_dir in \
    "$HOME/.config/chromium/NativeMessagingHosts" \
    "$HOME/.config/chromium-meet/NativeMessagingHosts" \
    "$HOME/.config/chromium-calendar/NativeMessagingHosts" \
    "$HOME/.config/net.imput.helium/NativeMessagingHosts"; do
    mkdir -p "$nmh_dir"
    cp "$MANIFEST_SRC" "$nmh_dir/me.memes.collection.json"
    echo "  Registered: $nmh_dir"
done

# Firefox native messaging host
FIREFOX_NMH="$HOME/.mozilla/native-messaging-hosts"
mkdir -p "$FIREFOX_NMH"
cp "$MANIFEST_SRC" "$FIREFOX_NMH/me.memes.collection.json"
echo "  Registered Firefox native messaging host"

echo ""
echo "=== Loading the extension ==="
echo ""
echo "Chromium / Helium / any Chromium-based:"
echo "  1. Open chrome://extensions"
echo "  2. Enable 'Developer mode' (top-right toggle)"
echo "  3. Click 'Load unpacked'"
echo "  4. Select: $EXTENSION_DIR"
echo ""
echo "Firefox:"
echo "  1. Open about:debugging#/runtime/this-firefox"
echo "  2. Click 'Load Temporary Add-on'"
echo "  3. Select: $EXTENSION_DIR/manifest.json"
echo ""
echo "=== Usage ==="
echo "  Right-click any image > Save to Meme Collection"
echo "  Image is saved to ~/.local/share/memes/ and copied to clipboard"
