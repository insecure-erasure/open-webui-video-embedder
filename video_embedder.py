"""
title: Video Embedder
author: Insecure Erasure
description: Uses yt-dlp to extract video metadata from supported sites and returns a Rich UI embed (HTMLResponse) that Open WebUI renders inline.
required_open_webui_version: 0.5.0
requirements: yt-dlp
version: 0.3.0
licence: MIT
"""

import asyncio
import html
import logging
import math
import re

from pydantic import BaseModel
from yt_dlp import YoutubeDL

from fastapi.responses import HTMLResponse

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
#  YouTube fast-path (no yt-dlp)
# ──────────────────────────────────────────────

# YouTube's extract_info is unreliable (bot checks / rate limiting can fail
# even for perfectly embeddable videos), so we build the embed directly from
# the video ID in the URL — no yt-dlp call needed. yt-dlp stays as a fallback
# for every other site (and for unrecognizable YouTube URLs).

_YOUTUBE_ID_RE = re.compile(r"(?:youtube\.com|youtu\.be)/(?:watch\?v=|shorts/|embed/|live/|v/)?([A-Za-z0-9_-]{11})")


def _get_youtube_id(url: str) -> str | None:
    """Extract a YouTube video ID directly from the URL (watch, youtu.be, shorts, embed, live)."""
    m = _YOUTUBE_ID_RE.search(url)
    return m.group(1) if m else None


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
#  Rich UI embed (HTMLResponse)
# ──────────────────────────────────────────────

# The tool returns a bare HTMLResponse (no tuple). Open WebUI's middleware
# detects it, emits the `embeds` event via Socket.IO, and the frontend
# renders it inline as a sandboxed iframe. The LLM never sees the HTML and
# receives only the middleware's generic message.
#
# Sizing (see DESIGN.md §6/§10 in open-webui-comfy-tools):
#  - `vh`/`vw` inside the sandboxed iframe refer to the iframe box (~150px
#    initial), NOT the browser viewport. Any viewport cap is expressed via
#    `screen.availHeight` (readable in the sandbox): 65% cap.
#  - The video's real aspect ratio comes from `loadedmetadata`
#    (`videoWidth`/`videoHeight`) — never a made-up ratio. yt-dlp's
#    metadata dimensions are used as a provisional `data-ar` until the real
#    one arrives.
#  - `reportHeight()` keeps the iframe at the content's real height.

def _aspect_ratio(width: int | None, height: int | None) -> str:
    """Return a 'w/h' aspect-ratio string from media dimensions, 16/9 fallback."""
    if width and height:
        g = math.gcd(width, height)
        return f"{width // g}/{height // g}"
    return "16/9"


def _build_iframe_html(embed_url: str, title: str = "", width: int | None = None, height: int | None = None) -> str:
    """Build a `.player` fragment containing a site iframe embed."""
    src = html.escape(embed_url, quote=True)
    safe_title = html.escape(title, quote=True)
    ar = _aspect_ratio(width, height)
    return (
        f'<div class="player" data-ar="{ar}">'
        f'<iframe src="{src}" title="{safe_title}" allow="autoplay;fullscreen" '
        f'allowfullscreen loading="lazy"></iframe>'
        f"</div>"
    )


def _build_video_html(video_url: str, width: int | None = None, height: int | None = None) -> str:
    """Build a `.player` fragment containing a native `<video>` element (MP4 or HLS)."""
    src = html.escape(video_url, quote=True)
    ar = _aspect_ratio(width, height)
    return (
        f'<div class="player" data-ar="{ar}">'
        f'<video src="{src}" autoplay muted loop playsinline controls preload="metadata"></video>'
        f"</div>"
    )


def _build_player_document(players: list[str]) -> str:
    """Combine `.player` fragments into a self-contained HTML document.

    A single sizing script fits every player to the chat container width
    (height capped at 65% of the available screen height) and reports the
    document height to the parent so the iframe hugs the content. Videos
    are re-fit on `loadedmetadata`/`loadeddata`/`canplay` (real aspect
    ratio), iframes use their `data-ar` (from yt-dlp metadata, 16/9
    fallback).
    """
    joined = "\n".join(players)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{{
  color-scheme:light dark;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;overflow:hidden;margin:0;padding:0}}
body{{display:flex;flex-direction:column;align-items:center;gap:16px;padding:16px;background:transparent}}
.player{{max-width:100%;overflow:hidden;border-radius:12px;background:#000}}
.player video,.player iframe{{display:block;width:100%;height:100%;border:0;object-fit:contain;border-radius:12px;background:#000}}
</style>
</head>
<body>
{joined}
<script>
const players=[...document.querySelectorAll('.player')];
function reportHeight(){{parent.postMessage({{type:'iframe:height',height:document.documentElement.scrollHeight}},'*')}}
function ratioOf(p){{
  const v=p.querySelector('video');
  if(v&&v.videoWidth>0&&v.videoHeight>0)return v.videoWidth/v.videoHeight;
  const a=(p.dataset.ar||'16/9').split('/').map(Number);
  return a[0]>0&&a[1]>0?a[0]/a[1]:16/9;
}}
function fit(){{
  // Height cap: 65% of the available screen height (screen.availHeight is
  // readable inside the sandbox; vh/vw units refer to the iframe box and
  // are useless here). The width derives from the container width and the
  // aspect ratio; the height never overflows the available screen space.
  const maxH=(screen.availHeight||screen.height||0)*0.65;
  const cw=document.documentElement.clientWidth;
  for(const p of players){{
    const r=ratioOf(p);
    let w=cw;
    if(maxH>0){{const wByH=maxH*r;if(wByH>0&&wByH<w)w=wByH;}}
    p.style.width=w+'px';
    p.style.height=(w/r)+'px';
  }}
  reportHeight();
}}
for(const v of document.querySelectorAll('video')){{
  v.addEventListener('loadedmetadata',fit);
  v.addEventListener('loadeddata',fit);
  v.addEventListener('canplay',fit);
}}
window.addEventListener('load',fit);
addEventListener('resize',fit);
new ResizeObserver(fit).observe(document.body);
fit();
</script>
</body>
</html>
"""


# ──────────────────────────────────────────────
#  Main embedding logic
# ──────────────────────────────────────────────

def _process_url(url: str) -> dict:
    """
    Process a video URL and return:
      - embed_html: ready-to-use `.player` HTML fragment
      - metadata: dict with video info
      - error: message if failed
    """
    # YouTube fast-path: yt-dlp's extract_info is unreliable for YouTube
    # (bot checks / rate limiting), but the video ID in the URL is enough to
    # build the official embed iframe. Skipping yt-dlp here makes YouTube
    # embeds work even when yt-dlp would fail.
    yt_id = _get_youtube_id(url)
    if yt_id:
        embed_url = f"https://www.youtube.com/embed/{yt_id}?autoplay=1&mute=1&rel=0"
        return {
            "embed_html": _build_iframe_html(embed_url, title="YouTube video", width=1920, height=1080),
            "metadata": {
                "title": f"YouTube video {yt_id}",
                "webpage_url": url,
                "stream_url": f"https://www.youtube.com/watch?v={yt_id}",
            },
        }

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
            embed_html = _build_video_html(direct_mp4, width=w, height=h)
            stream_url = direct_mp4
        else:
            best = _get_best_format(data)
            if best:
                url_best = best.get("url", "")
                embed_html = _build_video_html(url_best, width=w, height=h)
                stream_url = url_best
            else:
                embed_html = ""

    metadata = {
        "title": data.get("title", "?"),
        "webpage_url": webpage_url,
        "stream_url": stream_url,
    }

    return {"embed_html": embed_html, "metadata": metadata}


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
    ):
        """
        Generate a Rich UI embed (HTMLResponse) with the video player(s) for one or more video page URLs.
        Pass the URL of the video page itself (e.g. the page you watch the video on),
        not the direct CDN/MP4 link. This tool uses yt-dlp to extract metadata.

        Terminal result: the player is rendered inline in the chat via a
        sandboxed iframe (self-contained, autoplay muted loop, native
        controls). The LLM never sees the HTML and receives only the
        middleware's generic message — acknowledge that the video(s) were
        embedded and do not fabricate URLs.

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

        document = _build_player_document(embeds)
        return HTMLResponse(content=document, headers={"Content-Disposition": "inline"})
