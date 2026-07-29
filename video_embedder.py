"""
title: Video Embedder
author: Insecure Erasure
description: Extract direct video URLs from 1800+ sites via yt-dlp, returns embed-ready HTML. Supports RedGIFs, xHamster, YouTube, PornHub, XVideos and many more.
required_open_webui_version: 0.5.0
requirements: yt-dlp
version: 0.1.0
licence: MIT
"""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path

from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Assets directory resolution
# ──────────────────────────────────────────────

# Open WebUI does NOT expose internal variables to the tool (no TOOL_ID, no TOOL_NAME).
# The tool_id is known in load_tool_module_by_id() but never passed to the
# module namespace via exec() [plugin.py:82-129].
# Also __file__ points to a temp file (/tmp/...), not the real location.
#
# Strategy:
#   - DATA_DIR: env var that Open WebUI exposes [env.py:97]
#   - TOOL_NAME: hardcoded constant for this tool
#   - Combined: {DATA_DIR}/cache/tools/{TOOL_NAME}/
#   - Generic env var override: TOOL_ASSETS_DIR


# Tool name (for cache paths and internal references)
TOOL_NAME = "video-embedder"


def _resolve_assets_dir() -> Path:
    """Resolve the assets directory for this tool.

    Resolution order:
      1. TOOL_ASSETS_DIR env var (explicit override)
      2. Open WebUI standard path: $DATA_DIR/cache/tools/$TOOL_NAME/
      3. Script directory (local development fallback)
    """
    # 1. Explicit override via generic env var
    env = os.environ.get("TOOL_ASSETS_DIR")
    if env:
        p = Path(env)
        if p.exists():
            logger.debug(f"Assets dir from env: {p}")
            return p
        logger.warning(f"TOOL_ASSETS_DIR set but not found: {p}")

    # 2. Open WebUI canonical path
    data_dir = os.environ.get("DATA_DIR", "/app/backend/data")
    owui_cache = Path(data_dir) / "cache" / "tools" / TOOL_NAME
    if owui_cache.exists():
        logger.debug(f"Assets dir from Open WebUI cache: {owui_cache}")
        return owui_cache

    # 3. Fallback: alongside the script (local dev)
    script_dir = Path(__file__).parent.resolve()
    logger.debug(f"Assets dir from script location: {script_dir}")
    return script_dir


ASSETS_DIR = _resolve_assets_dir()


# ──────────────────────────────────────────────
#  Extractor → embed method mapping
# ──────────────────────────────────────────────

# Sites known to lack CORS on their CDNs
# requiring their own site iframe
IFRAME_EXTRACTORS = {
    "RedGifs": lambda id: f"https://www.redgifs.com/ifr/{id}",
    "XHamster": lambda id: f"https://xhamster.com/embed/{id}",
    "PornHub": lambda id: f"https://www.pornhub.com/embed/{id}",
    "XVideos": lambda id: f"https://www.xvideos.com/embedframe/{id}",
    "XHamsterEmbed": lambda id: f"https://xhamster.com/embed/{id}",
    "RedTube": lambda id: f"https://www.redtube.com/embed/{id}",
    "YouPorn": lambda id: f"https://www.youporn.com/embed/{id}",
    "SpankBang": lambda id: f"https://spankbang.com/embed/{id}",
    "EPORNER": lambda id: f"https://www.eporner.com/embed/{id}",
}

# Sites with known iframe URL patterns
IFRAME_WEBPAGE_PATTERNS = {
    "youtube": lambda id: f"https://www.youtube.com/embed/{id}",
    "Youtube": lambda id: f"https://www.youtube.com/embed/{id}",
}

# Combined map
EMBED_MAP = {}
EMBED_MAP.update(IFRAME_EXTRACTORS)
EMBED_MAP.update(IFRAME_WEBPAGE_PATTERNS)


# ──────────────────────────────────────────────
#  Utilities
# ──────────────────────────────────────────────

def _run_ytdlp(args: list[str]) -> dict | None:
    """Run yt-dlp and return parsed JSON."""
    cmd = ["yt-dlp", "--dump-json"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning(f"yt-dlp error: {result.stderr[:500]}")
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out")
        return None
    except json.JSONDecodeError:
        logger.warning("yt-dlp returned invalid JSON")
        return None
    except FileNotFoundError:
        logger.warning("yt-dlp not found")
        return None


def _format_duration(seconds: int) -> str:
    """Format duration to mm:ss or h:mm:ss."""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_number(n: int) -> str:
    """Format large numbers (1.2M, 43K, etc)."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _get_best_format(data: dict) -> dict | None:
    """Return the best format (highest resolution, non-mhtml)."""
    formats = data.get("formats", [])
    if not formats:
        return None

    # Prioritize direct MP4 over HLS
    best = None
    for f in formats:
        ext = f.get("ext", "")
        proto = f.get("protocol", "")
        if ext == "mhtml" or proto == "mhtml":
            continue
        height = f.get("height") or 0
        if best is None or height > (best.get("height") or 0):
            # Prefer direct MP4 over HLS at same resolution
            if best and height == (best.get("height") or 0):
                if ext == "mp4" and proto == "https":
                    best = f
            else:
                best = f
    return best


def _get_best_direct_mp4(data: dict) -> str | None:
    """Find the best direct MP4 (https, mp4) among formats."""
    formats = data.get("formats", [])
    best = None
    for f in formats:
        if f.get("ext") == "mp4" and f.get("protocol") == "https":
            height = f.get("height") or 0
            if best is None or height > (best.get("height") or 0):
                best = f
    return best["url"] if best else None


def _get_duration_str(data: dict) -> str:
    dur = data.get("duration")
    if dur:
        return _format_duration(int(dur))
    return "?"


def _get_view_count(data: dict) -> str:
    vc = data.get("view_count")
    if vc is not None:
        return _format_number(int(vc))
    return "?"


def _get_uploader(data: dict) -> str:
    up = data.get("uploader", data.get("channel", ""))
    return up or "?"


def _get_resolution_str(data: dict) -> str:
    w = data.get("width")
    h = data.get("height")
    if w and h:
        return f"{w}×{h}"
    return "?"


# ──────────────────────────────────────────────
#  HTML Templates
# ──────────────────────────────────────────────

# Default inline templates (always available)
_HTML_IFRAME_TEMPLATE = """<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;background:#000;border-radius:8px;margin:12px 0">
  <iframe src="{embed_url}" title="{safe_title}"
    style="position:absolute;top:0;left:0;width:100%;height:100%;border:none"
    allow="autoplay; fullscreen" allowfullscreen loading="lazy">
  </iframe>
</div>"""

_HTML_VIDEO_TEMPLATE = """<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;background:#000;border-radius:8px;margin:12px 0">
  <video controls style="position:absolute;top:0;left:0;width:100%;height:100%" preload="metadata" playsinline>
    <source src="{video_url}" type="video/mp4">
  </video>
</div>"""

_HTML_HLS_TEMPLATE = """<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;background:#000;border-radius:8px;margin:12px 0">
  <video controls style="position:absolute;top:0;left:0;width:100%;height:100%" preload="metadata">
    <source src="{video_url}" type="application/x-mpegURL">
  </video>
  <p style="color:#888;font-size:12px;text-align:center;margin:4px 0">⚠️ HLS stream — may require a compatible browser</p>
</div>"""


def _load_template(name: str) -> str:
    """
    Load a template from ASSETS_DIR if the file exists,
    otherwise return the default inline template.
    """
    tpl_path = ASSETS_DIR / "templates" / name
    if tpl_path.exists():
        logger.debug(f"Loading template from file: {tpl_path}")
        return tpl_path.read_text(encoding="utf-8")
    # Fallback to inline
    inline_map = {
        "iframe.html": _HTML_IFRAME_TEMPLATE,
        "video.html": _HTML_VIDEO_TEMPLATE,
        "hls.html": _HTML_HLS_TEMPLATE,
    }
    return inline_map.get(name, "")


def _build_iframe_html(embed_url: str, title: str = "") -> str:
    """Generate iframe embed HTML."""
    safe_title = title.replace('"', "&quot;")
    tpl = _load_template("iframe.html")
    return tpl.replace("{embed_url}", embed_url).replace("{safe_title}", safe_title)


def _build_video_html(video_url: str, title: str = "", m3u8: bool = False) -> str:
    """Generate <video> embed HTML for direct MP4 or HLS."""
    if m3u8:
        tpl = _load_template("hls.html")
    else:
        tpl = _load_template("video.html")
    return tpl.replace("{video_url}", video_url)


def _build_metadata_table(data: dict) -> str:
    """Build markdown metadata table."""
    rows = [
        ("Title", data.get("title", "?")),
        ("Duration", data.get("duration", "?")),
        ("Uploader", data.get("uploader", "?")),
        ("Views", data.get("view_count", "?")),
        ("Resolution", data.get("resolution", "?")),
        ("Extractor", data.get("extractor", "?")),
    ]
    lines = ["| Field | Value |", "|---|---|"]
    for label, value in rows:
        lines.append(f"| **{label}** | {value} |")
    return "\n".join(lines)


def _build_link_row(webpage_url: str, stream_url: str | None, extractor: str) -> str:
    """Build useful links: original page and direct stream."""
    lines = []
    if webpage_url:
        lines.append(f"- **🔗 Original:** [{webpage_url}]({webpage_url})")
    if stream_url:
        if not any(ex in extractor for ex in ["youtube", "Youtube"]):
            lines.append(f"- **📺 Stream:** `{stream_url}`")
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Main embedding logic
# ──────────────────────────────────────────────

def _process_url(url: str) -> dict:
    """
    Process a video URL and return:
      - embed_html: ready-to-use HTML
      - metadata: dict with video info
      - error: message if failed
    """
    # 1. Call yt-dlp
    data = _run_ytdlp([url])
    if data is None:
        return {"error": f"Could not extract info from URL. Is it supported by yt-dlp?"}

    extractor = data.get("extractor", "")
    video_id = data.get("id", "")
    title = data.get("title", "Video")
    webpage_url = data.get("webpage_url", url)

    # 2. Determine embedding method
    embed_html = ""
    stream_url = None

    if extractor in EMBED_MAP:
        # Use site iframe
        iframe_url = EMBED_MAP[extractor](video_id)
        embed_html = _build_iframe_html(iframe_url, title)
        stream_url = _get_best_direct_mp4(data) or data.get("url")

    else:
        # Generic: try direct MP4
        direct_mp4 = _get_best_direct_mp4(data)
        if direct_mp4:
            embed_html = _build_video_html(direct_mp4, title)
            stream_url = direct_mp4
        else:
            # Fallback: HLS or yt-dlp direct URL
            best = _get_best_format(data)
            if best:
                url_best = best.get("url", "")
                is_m3u8 = "m3u8" in (best.get("protocol", "") or "") or ".m3u8" in url_best
                embed_html = _build_video_html(url_best, title, m3u8=is_m3u8)
                stream_url = url_best
            else:
                # Last resort: link to webpage
                embed_html = f"⚠️ Could not generate embed. [Open video on web]({webpage_url})"

    # 3. Build metadata
    metadata = {
        "id": video_id,
        "extractor": extractor,
        "title": data.get("title", "?"),
        "duration": _get_duration_str(data),
        "uploader": _get_uploader(data),
        "view_count": _get_view_count(data),
        "resolution": _get_resolution_str(data),
        "webpage_url": webpage_url,
        "stream_url": stream_url,
    }

    return {"embed_html": embed_html, "metadata": metadata}


def _format_single_result(result: dict) -> str:
    """Format a single URL result as markdown + HTML metadata (text only)."""
    if "error" in result:
        return f"❌ **Error:** {result['error']}"

    meta = result["metadata"]
    lines = [
        f"### 🎬 {meta['title']}",
        "",
        _build_metadata_table(result["metadata"]),
        "",
        _build_link_row(
            meta["webpage_url"],
            meta["stream_url"],
            meta["extractor"]
        ),
    ]
    return "\n".join(lines)


def _build_players_html(results: list[dict]) -> str:
    """Build a complete HTML document with all video players for rich UI embed."""
    players = []
    for r in results:
        if "error" in r:
            continue
        embed = r.get("embed_html", "")
        if embed:
            players.append(f'<div class="player-item">{embed}</div>')

    if not players:
        return ""

    return f"""<!DOCTYPE html>
<html>
<head>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: system-ui, sans-serif; padding: 8px; background: transparent; }}
  .player-item {{ margin-bottom: 16px; }}
  .player-item:last-child {{ margin-bottom: 0; }}
</style>
</head>
<body>
{"".join(players)}
<script>
  (function() {{
    function rh() {{ var h = document.documentElement.scrollHeight; parent.postMessage({{ type: 'iframe:height', height: h }}, '*'); }}
    window.addEventListener('load', rh);
    new ResizeObserver(rh).observe(document.body);
  }})();
</script>
</body>
</html>"""


def _build_context(results: list[dict]) -> str:
    """Build text context for the LLM: metadata for each video, no raw HTML."""
    lines = []
    success_count = sum(1 for r in results if "error" not in r)
    error_count = len(results) - success_count
    summary = f"Video Embedder — {success_count} embedded"
    if error_count:
        summary += f", {error_count} failed"
    lines.append(summary)

    for i, r in enumerate(results, 1):
        if "error" in r:
            lines.append(f"Video {i}: ❌ Error — {r['error']}")
        else:
            meta = r["metadata"]
            lines.append(
                f"Video {i}: {meta['title']} ({meta['duration']}) — "
                f"{meta['uploader']} — {meta['view_count']} views — {meta['resolution']}"
            )
            lines.append(f"  Original: {meta['webpage_url']}")
            if meta["stream_url"]:
                lines.append(f"  Stream: {meta['stream_url']}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Open WebUI Tool class
# ──────────────────────────────────────────────

class Tools:
    class Valves(BaseModel):
        ytdlp_timeout: int = Field(
            default=60,
            description="Timeout in seconds for each yt-dlp call",
        )

    class UserValves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()

    async def _emit_status(self, __event_emitter__, description: str, done: bool = False):
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": description, "done": done}}
            )

    async def embed_videos(
        self,
        urls: list[str],
        __event_emitter__=None,
    ) -> str:
        """
        Embed one or more video URLs. Returns a rich HTML player that renders
        inline in the chat, plus metadata context visible to the model.

        :param urls: One or more direct video page URLs
        :return: Inline HTML player(s) with metadata
        """
        if not urls:
            return "❌ No URLs provided."

        loop = asyncio.get_event_loop()
        results = []

        for i, url in enumerate(urls, 1):
            await self._emit_status(
                __event_emitter__,
                f"[{i}/{len(urls)}] Extracting: {url[:80]}..."
            )
            result = await loop.run_in_executor(None, _process_url, url)
            results.append(result)

        await self._emit_status(__event_emitter__, "All videos extracted", done=True)

        players_html = _build_players_html(results)
        context = _build_context(results)

        if not players_html:
            # All failed — return plain text
            return context

        return HTMLResponse(
            content=players_html,
            headers={"Content-Disposition": "inline"},
        ), context
