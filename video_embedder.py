"""
title: Video Embedder
author: Insecure Erasure
description: Uses yt-dlp to extract video metadata from supported sites and returns embed-ready HTML.
required_open_webui_version: 0.5.0
requirements: yt-dlp
version: 0.1.0
licence: MIT
"""

import asyncio
import json
import logging
import math

from html.parser import HTMLParser
from pydantic import BaseModel
from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)





# ──────────────────────────────────────────────
#  Generic embed URL construction
# ──────────────────────────────────────────────

# Known embed URL patterns for sites whose CDNs lack CORS
_EMBED_URLS = {
    "youtube.com": lambda id: f"https://www.youtube.com/embed/{id}",
    "youtu.be": lambda id: f"https://www.youtube.com/embed/{id}",
    "redgifs.com": lambda id: f"https://www.redgifs.com/ifr/{id}",
    "xvideos.com": lambda id: f"https://www.xvideos.com/embedframe/{id}",
}


def _get_embed_url(extractor: str, video_id: str, webpage_url_domain: str | None) -> str | None:
    """Return known embed URL for a site, or None."""
    builder = _EMBED_URLS.get(webpage_url_domain or "")
    return builder(video_id) if builder else None


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
_AR_W = 16
_AR_H = 9
_AR = "16/9"

_HTML_IFRAME_TEMPLATE = '<body style="margin:0;background:#0d0d0d;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center"><div style="width:100%;height:100%;max-width:calc(100vh*{ar_w}/{ar_h});max-height:calc(100vw*{ar_h}/{ar_w});aspect-ratio:{ar};border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5)"><iframe src="{embed_url}" title="{safe_title}" allow="autoplay;fullscreen" allowfullscreen loading="lazy" style="width:100%;height:100%;border:0;background:#0d0d0d"></iframe></div></body>'

_HTML_VIDEO_TEMPLATE = '<body style="margin:0;background:#0d0d0d;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center"><div style="width:100%;height:100%;max-width:calc(100vh*{ar_w}/{ar_h});max-height:calc(100vw*{ar_h}/{ar_w});aspect-ratio:{ar};border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5)"><video src="{video_url}" controls preload="metadata" playsinline style="width:100%;height:100%;border:0;background:#0d0d0d"></video></div></body>'

_HTML_HLS_TEMPLATE = '<body style="margin:0;background:#0d0d0d;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center"><div style="width:100%;height:100%;max-width:calc(100vh*{ar_w}/{ar_h});max-height:calc(100vw*{ar_h}/{ar_w});aspect-ratio:{ar};border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5)"><video src="{video_url}" controls preload="metadata" style="width:100%;height:100%;border:0;background:#0d0d0d"></video></div></body>'





def _build_iframe_html(embed_url: str, title: str = "", width: int | None = None, height: int | None = None) -> str:
    """Generate iframe embed HTML."""
    safe_title = title.replace('"', "&quot;")
    ar_w, ar_h, ar = _calc_aspect_ratio(width, height)
    return (_HTML_IFRAME_TEMPLATE.replace("{embed_url}", embed_url)
            .replace("{safe_title}", safe_title)
            .replace("{ar_w}", str(ar_w))
            .replace("{ar_h}", str(ar_h))
            .replace("{ar}", ar))


def _build_video_html(video_url: str, title: str = "", m3u8: bool = False, width: int | None = None, height: int | None = None) -> str:
    """Generate <video> embed HTML for direct MP4 or HLS."""
    tpl = _HTML_HLS_TEMPLATE if m3u8 else _HTML_VIDEO_TEMPLATE
    ar_w, ar_h, ar = _calc_aspect_ratio(width, height)
    return (tpl.replace("{video_url}", video_url)
            .replace("{ar_w}", str(ar_w))
            .replace("{ar_h}", str(ar_h))
            .replace("{ar}", ar))


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

    w = data.get("width")
    h = data.get("height")

    iframe_url = _get_embed_url(extractor, video_id, data.get("webpage_url_domain"))
    if iframe_url:
        embed_html = _build_iframe_html(iframe_url, title, width=w, height=h)
        stream_url = _get_best_direct_mp4(data) or data.get("url")
    else:
        direct_mp4 = _get_best_direct_mp4(data)
        if direct_mp4:
            embed_html = _build_video_html(direct_mp4, title, width=w, height=h)
            stream_url = direct_mp4
        else:
            best = _get_best_format(data)
            if best:
                url_best = best.get("url", "")
                is_m3u8 = "m3u8" in (best.get("protocol", "") or "") or ".m3u8" in url_best
                embed_html = _build_video_html(url_best, title, m3u8=is_m3u8, width=w, height=h)
                stream_url = url_best
            else:
                embed_html = ""



    metadata = {
        "title": data.get("title", "?"),
        "webpage_url": webpage_url,
        "stream_url": stream_url,
    }

    return {"embed_html": embed_html, "metadata": metadata}


def _calc_aspect_ratio(width: int | None, height: int | None) -> tuple[int, int, str]:
    """Return (ar_w, ar_h, "ar_w/ar_h") from dimensions, defaults to 16/9."""
    if width and height:
        g = math.gcd(width, height)
        ar_w = width // g
        ar_h = height // g
        return ar_w, ar_h, f"{ar_w}/{ar_h}"
    return _AR_W, _AR_H, _AR


class _BodyContentFinder(HTMLParser):
    """Extract the content inside <body> from a full HTML document."""
    def __init__(self):
        super().__init__()
        self._in_body = False
        self._depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self._in_body = True
            return
        if self._in_body:
            self._parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == "body":
            self._in_body = False
            return
        if self._in_body:
            self._parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self._in_body:
            self._parts.append(data)

    def handle_startendtag(self, tag, attrs):
        if self._in_body:
            self._parts.append(self.get_starttag_text())


def _extract_body_content(html: str) -> str:
    """Return the HTML content inside <body> (the <div> with aspect-ratio)."""
    parser = _BodyContentFinder()
    parser.feed(html)
    return "".join(parser._parts)


def _combine_html(html_list: list[str]) -> str:
    """Combine multiple embed HTML fragments into a single HTML document.
    Each embed keeps its own <div> with its specific aspect-ratio.
    """
    if len(html_list) == 1:
        return html_list[0]
    divs = []
    for html in html_list:
        content = _extract_body_content(html)
        if content:
            divs.append(content)
    joined = "".join(divs)
    return f'<body style="margin:0;background:#0d0d0d;width:100vw;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:16px 0;box-sizing:border-box">{joined}</body>'


def _build_embed_code(embed_html: str) -> str:
    """Wrap embed HTML in an instruction for the LLM."""
    return f'Output this HTML exactly, without modifying it:\n\n```html\n{embed_html}\n```'


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

        embeds = []
        for i, r in enumerate(results, 1):
            if "error" in r:
                await self._emit_status(__event_emitter__, f"⚠️ Skipped video {i}: {r['error']}")
                continue
            embed_html = r.get("embed_html", "")
            if not embed_html:
                await self._emit_status(__event_emitter__, f"⚠️ Skipped video {i}: no playable format found")
                continue
            embeds.append(embed_html)

        if not embeds:
            await self._emit_status(__event_emitter__, "❌ None of the videos could be embedded", done=True)
            return "❌ None of the videos could be embedded."

        combined = _combine_html(embeds)
        return _build_embed_code(combined)
