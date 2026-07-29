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

Examples: YouTube, Vimeo.

### ▶️ Direct video embed
For sites that offer **direct MP4** URLs (e.g., Vimeo), the tool generates a `<video>` tag using the highest-resolution MP4 available.

### 📡 HLS stream embed
For sites that only provide HLS streams (`.m3u8`), the tool falls back to a `<video>` tag pointing to the HLS URL.

## Format selection logic

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

**Returns:** HTML code blocks (one per video) that the LLM should output in its response.

## Templates

Embed HTML can be customized by placing template files in the tool's assets directory:

| Template file | Used for |
|---|---|
| `templates/iframe.html` | Iframe embeds |
| `templates/video.html` | Direct MP4 embeds |
| `templates/hls.html` | HLS stream embeds |

If a template file exists, it is loaded from disk. Otherwise, the built-in default template is used.

Template variables:
- `{embed_url}` — embed/src URL
- `{video_url}` — video source URL
- `{safe_title}` — video title (HTML-escaped, only in iframe template)

### Default templates location

Resolution order:
1. `$TOOL_ASSETS_DIR` environment variable (explicit override)
2. `$DATA_DIR/cache/tools/video-embedder/` (Open WebUI standard cache path)
3. Script directory (local development fallback)

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

### Valve configuration

The tool exposes one configurable valve:

| Valve | Type | Default | Description |
|---|---|---|---|
| `ytdlp_timeout` | `int` | `60` | Timeout in seconds for each yt-dlp call |

## License

MIT
