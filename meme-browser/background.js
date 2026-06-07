// Meme Collection browser extension
// Adds right-click "Save to Meme Collection" on images

const HOST_NAME = "me.memes.collection";

// Minimum image size (bytes) to trigger chunked encoding
const LARGE_IMAGE_THRESHOLD = 1 << 20; // 1 MiB
const CHUNK_SIZE = 8192; // 8 KiB chunks for stack-safe base64

// Create context menu on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "save-to-meme-collection",
    title: "Save to Meme Collection",
    contexts: ["image"],
  });
});

/**
 * Convert an ArrayBuffer to a base64 string efficiently.
 * Uses chunked String.fromCharCode to avoid stack overflow on large images.
 */
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  const len = bytes.length;

  // Fast path for small buffers — single apply is safe
  if (len < LARGE_IMAGE_THRESHOLD) {
    let binary = "";
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  // Chunked path for large images — avoids call-stack limit
  let binary = "";
  for (let i = 0; i < len; i += CHUNK_SIZE) {
    const chunk = bytes.subarray(i, i + CHUNK_SIZE);
    binary += String.fromCharCode.apply(null, chunk);
  }
  return btoa(binary);
}

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "save-to-meme-collection" || !info.srcUrl) {
    return;
  }

  try {
    // Fetch the image with credentials (works for most sites)
    const response = await fetch(info.srcUrl, {
      credentials: "include",
      cache: "force-cache",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const blob = await response.blob();
    const mimeType = blob.type || "image/png";
    const buffer = await blob.arrayBuffer();
    const data = arrayBufferToBase64(buffer);

    // Send to native host
    const host = chrome.runtime.connectNative(HOST_NAME);

    host.onMessage.addListener((response) => {
      const notification = {
        type: "basic",
        iconUrl: "icons/icon48.png",
        title: response.success
          ? "Meme Collection"
          : "Meme Collection — Error",
        message: response.success
          ? `Saved: ${response.filename}`
          : response.error || "Failed to save image",
      };
      chrome.notifications.create(notification);
      host.disconnect();
    });

    host.onDisconnect.addListener(() => {
      if (chrome.runtime.lastError) {
        chrome.notifications.create({
          type: "basic",
          iconUrl: "icons/icon48.png",
          title: "Meme Collection — Error",
          message: "Native host not found. Run setup script?",
        });
      }
    });

    host.postMessage({
      action: "save",
      mimeType: mimeType,
      data: data,
    });
  } catch (err) {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon48.png",
      title: "Meme Collection — Error",
      message: err.message,
    });
  }
});
