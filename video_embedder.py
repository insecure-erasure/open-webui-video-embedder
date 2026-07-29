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
from pathlib import Path

from pydantic import BaseModel, Field
from yt_dlp import YoutubeDL

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
#  Extractor -> embed method mapping
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

def _run_ytdlp(args: list[str]) -> tuple[dict | None, str | None]:
    """Run yt-dlp and return (data, error).
    Returns (dict, None) on success, (None, str) on failure.
    """
    url = args[0] if args else ""
    try:
        with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            data = ydl.extract_info(url, download=False)
            return data, None
    except Exception as e:
        msg = str(e).strip()
        logger.warning(f"yt-dlp error: {msg}")
        return None, msg


def _format_duration(seconds: int) -> str:
    """Format duration to mm:ss or h:mm:ss."""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _get_best_format(data: dict) -> dict | None:
    """Return the best format (highest resolution, non-mhtml)."""
    formats = data.get("formats", [])
    if not formats:
        return None

    best = None
    for f in formats:
        ext = f.get("ext", "")
        proto = f.get("protocol", "")
        if ext == "mhtml" or proto == "mhtml":
            continue
        height = f.get("height") or 0
        if best is None or height > (best.get("height") or 0):
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


# ──────────────────────────────────────────────
#  HTML Templates
# ──────────────────────────────────────────────

# Default inline templates (always available)
_HTML_IFRAME_TEMPLATE = """<body style="margin:0;background:#0d0d0d;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center">
<div style="width:100%;height:100%;max-width:calc((100vh*9)/16);max-height:calc((100vw*16)/9);aspect-ratio:9/16;border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5)">
<iframe src="{embed_url}" title="{safe_title}" allow="autoplay;fullscreen" allowfullscreen loading="lazy" style="width:100%;height:100%;border:0;background:#0d0d0d">
</iframe>
</div>
</body>"""

_HTML_VIDEO_TEMPLATE = """<body style="margin:0;background:#0d0d0d;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center">
<div style="width:100%;height:100%;max-width:calc((100vh*9)/16);max-height:calc((100vw*16)/9);aspect-ratio:9/16;border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5)">
<video src="{video_url}" controls preload="metadata" playsinline style="width:100%;height:100%;border:0;background:#0d0d0d"></video>
</div>
</body>"""

_HTML_HLS_TEMPLATE = """<body style="margin:0;background:#0d0d0d;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center">
<div style="width:100%;height:100%;max-width:calc((100vh*9)/16);max-height:calc((100vw*16)/9);aspect-ratio:9/16;border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5)">
<video src="{video_url}" controls preload="metadata" style="width:100%;height:100%;border:0;background:#0d0d0d"></video>
</div>
</body>"""


def _load_template(name: str) -> str:
    """
    Load a template from ASSETS_DIR if the file exists,
    otherwise return the default inline template.
    """
    tpl_path = ASSETS_DIR / "templates" / name
    if tpl_path.exists():
        logger.debug(f"Loading template from file: {tpl_path}")
        return tpl_path.read_text(encoding="utf-8")
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
    data, err = _run_ytdlp([url])
    if data is None:
        return {"error": err or "Could not extract info from URL"}

    extractor = data.get("extractor", "")
    video_id = data.get("id", "")
    title = data.get("title", "Video")
    webpage_url = data.get("webpage_url", url)

    embed_html = ""
    stream_url = None

    if extractor in EMBED_MAP:
        iframe_url = EMBED_MAP[extractor](video_id)
        embed_html = _build_iframe_html(iframe_url, title)
        stream_url = _get_best_direct_mp4(data) or data.get("url")

    else:
        direct_mp4 = _get_best_direct_mp4(data)
        if direct_mp4:
            embed_html = _build_video_html(direct_mp4, title)
            stream_url = direct_mp4
        else:
            best = _get_best_format(data)
            if best:
                url_best = best.get("url", "")
                is_m3u8 = "m3u8" in (best.get("protocol", "") or "") or ".m3u8" in url_best
                embed_html = _build_video_html(url_best, title, m3u8=is_m3u8)
                stream_url = url_best
            else:
                embed_html = ""

    metadata = {
        "title": data.get("title", "?"),
        "webpage_url": webpage_url,
        "stream_url": stream_url,
    }

    return {"embed_html": embed_html, "metadata": metadata}


import re


def _combine_html(html_list: list[str]) -> str:
    """Combine multiple embed HTML fragments into a single HTML document."""
    if len(html_list) == 1:
        return html_list[0]
    divs = []
    for html in html_list:
        m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL)
        if m:
            divs.append(m.group(1))
    return f"""<body style="margin:0;background:#0d0d0d;width:100vw;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:16px 0;box-sizing:border-box">
{"\n".join(divs)}
</body>"""


def _build_embed_code(embed_html: str) -> str:
    """Wrap embed HTML in an instruction for the LLM."""
    return f"Output this HTML code block:\n\n```html\n{embed_html}\n```"


# ──────────────────────────────────────────────
#  Open WebUI Tool class
# ──────────────────────────────────────────────

class Tools:
    class Valves(BaseModel):
        pass

    class UserValves(BaseModel):
        pass

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
        Generate embed HTML from one or more video page URLs.
        Pass the URL of the video page itself (e.g. the page you watch the video on),
        not the direct CDN/MP4 link. This tool uses yt-dlp to extract metadata.

        :param urls: One or more video page URLs
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

        errors = []
        embeds = []
        for i, r in enumerate(results, 1):
            if "error" in r:
                return f"❌ Video {i}: {r['error']}"
            embed_html = r.get("embed_html", "")
            if not embed_html:
                return f"❌ Video {i}: Could not generate embed for this URL."
            embeds.append(embed_html)

        combined = _combine_html(embeds)
        return _build_embed_code(combined)
