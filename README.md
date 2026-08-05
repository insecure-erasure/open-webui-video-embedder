# Video Embedder

An [Open WebUI](https://openwebui.com/) tool that uses `yt-dlp` to extract video metadata and generates **ready-to-embed HTML**. Supports direct MP4, HLS streams, and iframe embeds.

## How it works

1. You give it one or more video page URLs (e.g., from YouTube, Vimeo, Dailymotion, etc.)
2. It runs `yt-dlp` under the hood to extract metadata and available formats
3. It selects the **best quality format** automatically and generates embed HTML
4. The HTML is returned as a code block that the LLM can output for rendering

## Supported embed modes

The tool picks the best strategy depending on the source site:

### 🖼️ Iframe embed
For sites with known embed URLs, the tool generates an `<iframe>` pointing to the platform's official embed page. No CORS issues.

Currently mapped: **YouTube** (`youtube.com` / `youtu.be`).

### ▶️ Direct video embed
For sites that offer **direct HTTPS MP4** URLs (e.g., Vimeo), the tool generates a `<video>` tag using the highest-resolution MP4 available.

### 📡 HLS stream embed
For sites that only provide HLS streams (`.m3u8`), the tool falls back to a `<video>` tag pointing to the HLS URL (e.g., Dailymotion).

## Format selection logic

- **Direct HTTPS MP4** is preferred whenever available (progressive download, browser-playable)
- **Highest resolution** wins
- **MP4 over HLS** at the same resolution (prefers progressive download over streaming)
- **Skips `mhtml`** containers (not playable in browsers)
- Falls back to whatever format is available

## Usage (Open WebUI)

Once installed as an Open WebUI tool, the function `embed_videos` becomes available to the LLM:

```
embed_videos(urls=["https://www.youtube.com/watch?v=...", "https://vimeo.com/..."])
```

**Parameters:**
- `urls` — list of video page URLs to process

**Returns:** a single HTML code block containing all video embeds, which the LLM should output verbatim in its response.

## Embed HTML

The embed HTML is fully self-contained — the templates are built into the script (no external files required).

Three inline templates are used, one per embed mode:

| Template | Used for |
|---|---|
| iframe | Sites with known embed URLs |
| video | Direct MP4 embeds |
| HLS | HLS stream embeds |

Each embed is a `<body>` document with a centered, responsive container that:

- preserves the video's **aspect ratio**, computed from the yt-dlp metadata dimensions (`math.gcd`, 16/9 fallback)
- scales to fit the viewport (`100vw`/`100vh`) without distortion
- has rounded corners, a subtle shadow, and a dark background
- escapes the video title for the iframe `title` attribute

When multiple videos are requested, each keeps its own aspect-ratio container and all are combined into a single HTML document.

## Requirements

- **Python 3.10+**
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — must be installed and available in `PATH`
- Open WebUI (when deploying as a tool)

### Python dependencies (for development)

- `pydantic` — for the Valves model
- `pytest` — for running tests

## Development

### Running tests

```bash
# Install dependencies
pip install pytest

# Run tests
pytest tests/
```

The test suite covers:
- **Iframe path** — sites with known embed URLs
- **Direct MP4 path** — sites like Vimeo offering direct HTTPS MP4 files
- **HLS path** — sites like Dailymotion with only HLS/m3u8 streams
- **Webm fallback** — when webm is the best available format
- **No usable formats** — when only mhtml containers exist
- **Error handling** — when yt-dlp fails

### Configuration

The tool currently exposes **no configurable valves** (the `Valves` class is empty) and has no external configuration. All behavior is built in.

## License

MIT
