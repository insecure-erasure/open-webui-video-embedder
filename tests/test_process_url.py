"""Tests for _process_url with mocked yt-dlp — simulates every code path.

All fixtures use real, existing video IDs from supported sites.

Covers:
  - Iframe path  (sites with known embed URLs)
  - Direct MP4   (Vimeo — direct HTTPS MP4 formats)
  - HLS stream   (Dailymotion — only HLS/m3u8 formats)
  - Webm direct  (Dailymotion — webm format available)
  - No embed     (only mhtml format -> no embed HTML)
  - Error        (yt-dlp returns None)
"""

from unittest.mock import patch

import pytest

from video_embedder import _process_url


# ─── Fixtures: real video data ────────────────────────────────────────────

@pytest.fixture
def iframe_data():
    """RedGifs — real video from redgifs.com/watch/reflectingwellinformedgordonsetter."""
    return {
        "id": "reflectingwellinformedgordonsetter",
        "extractor": "RedGifs",
        "title": "Bikini Micro Bikini SFW TikTok",
        "webpage_url": "https://redgifs.com/watch/reflectingwellinformedgordonsetter",
        "webpage_url_domain": "redgifs.com",
        "url": "https://media.redgifs.com/ReflectingWellinformedGordonsetter.mp4",
        "duration": 8, "view_count": 339535,
        "uploader": "marilyn_merlot", "width": 1080, "height": 1920,
        "formats": [
            {"ext": "mp4", "protocol": "https", "height": 480,
             "url": "https://media.redgifs.com/ReflectingWellinformedGordonsetter-mobile.mp4"},
            {"ext": "mp4", "protocol": "https", "height": 1920,
             "url": "https://media.redgifs.com/ReflectingWellinformedGordonsetter.mp4"},
        ],
    }


@pytest.fixture
def direct_mp4_data():
    """Vimeo — Big Buck Bunny (vimeo.com/1084537), Creative Commons licensed."""
    return {
        "id": "1084537", "extractor": "vimeo",
        "title": "Big Buck Bunny",
        "webpage_url": "https://vimeo.com/1084537",
        "webpage_url_domain": "vimeo.com",
        "url": "https://player.vimeo.com/progressive_redirect/1084537/720p.mp4",
        "duration": 634,
        "formats": [
            {"ext": "mp4", "protocol": "https", "height": 720,
             "url": "https://player.vimeo.com/progressive_redirect/1084537/720p.mp4"},
            {"ext": "mp4", "protocol": "https", "height": 1080,
             "url": "https://player.vimeo.com/progressive_redirect/1084537/1080p.mp4"},
        ],
    }


@pytest.fixture
def hls_only_data():
    """Dailymotion — Big Buck Bunny 60fps (dailymotion.com/video/x9yfz8u). All formats are HLS."""
    return {
        "id": "x9yfz8u", "extractor": "dailymotion",
        "title": "Big Buck Bunny | Official Blender Foundation Short Film (HD, 60fps)",
        "webpage_url": "https://www.dailymotion.com/video/x9yfz8u",
        "webpage_url_domain": "dailymotion.com",
        "url": "https://vod3.cf.dmcdn.net/sec2(x9yfz8u)/video.m3u8",
        "duration": 634,
        "formats": [
            {"ext": "mp4", "protocol": "m3u8_native", "height": 720,
             "url": "https://vod3.cf.dmcdn.net/sec2(x9yfz8u_720)/video.m3u8"},
            {"ext": "mp4", "protocol": "m3u8_native", "height": 1080,
             "url": "https://vod3.cf.dmcdn.net/sec2(x9yfz8u_1080)/video.m3u8"},
        ],
    }


@pytest.fixture
def direct_webm_data():
    """Dailymotion — Big Buck Bunny (dailymotion.com/video/x24fho2). Lower-res webm + HLS."""
    return {
        "id": "x24fho2", "extractor": "dailymotion",
        "title": "Big Buck Bunny - Blender Foundation",
        "webpage_url": "https://www.dailymotion.com/video/x24fho2",
        "webpage_url_domain": "dailymotion.com",
        "url": "https://vod3.cf.dmcdn.net/sec2(x24fho2)/video.m3u8",
        "duration": 634,
        "formats": [
            {"ext": "webm", "protocol": "https", "height": 360,
             "url": "https://www.dailymotion.com/cdn/x24fho2.webm"},
            {"ext": "mp4", "protocol": "m3u8_native", "height": 720,
             "url": "https://vod3.cf.dmcdn.net/sec2(x24fho2_720)/video.m3u8"},
        ],
    }


@pytest.fixture
def no_usable_formats_data():
    return {
        "id": "weird987", "extractor": "generic",
        "title": "Some obscure stream",
        "webpage_url": "https://example.com/weird987",
        "webpage_url_domain": "example.com",
        "url": None, "duration": None,
        "formats": [{"ext": "mhtml", "protocol": "mhtml", "height": 9999}],
    }


# ─── Helpers ──────────────────────────────────────────────────────────────

def assert_iframe_html(html: str, *, embed_url: str, title: str, ar_w: int = 9, ar_h: int = 16):
    assert "iframe" in html
    assert embed_url in html
    assert "width:100vw" in html
    assert f"aspect-ratio:{ar_w}/{ar_h}" in html
    assert f"max-width:calc(100vh*{ar_w}/{ar_h})" in html


def assert_video_html(html: str, *, video_url: str, is_hls: bool = False, ar_w: int = 16, ar_h: int = 9):
    assert "video" in html
    assert "controls" in html
    assert video_url in html
    assert "width:100vw" in html
    assert f"max-height:calc(100vw*{ar_h}/{ar_w})" in html


# ─── Tests: iframe path (RedGifs) ────────────────────────────────────────

class TestIframePath:
    def test_returns_iframe_html(self, iframe_data):
        with patch("video_embedder._run_ytdlp", return_value=(iframe_data, None)):
            result = _process_url("https://redgifs.com/watch/reflectingwellinformedgordonsetter")

        assert "error" not in result
        assert_iframe_html(
            result["embed_html"],
            embed_url="https://www.redgifs.com/ifr/reflectingwellinformedgordonsetter",
            title="Bikini Micro Bikini SFW TikTok",
            ar_w=9, ar_h=16,
        )

    def test_metadata_has_title_and_urls(self, iframe_data):
        with patch("video_embedder._run_ytdlp", return_value=(iframe_data, None)):
            result = _process_url("https://redgifs.com/watch/reflectingwellinformedgordonsetter")

        meta = result["metadata"]
        assert meta["title"] == "Bikini Micro Bikini SFW TikTok"
        assert meta["webpage_url"] == "https://redgifs.com/watch/reflectingwellinformedgordonsetter"
        assert meta["stream_url"] == "https://media.redgifs.com/ReflectingWellinformedGordonsetter.mp4"


# ─── Tests: direct MP4 (Vimeo) ──────────────────────────────────────────

class TestDirectMp4Path:
    def test_returns_video_html(self, direct_mp4_data):
        with patch("video_embedder._run_ytdlp", return_value=(direct_mp4_data, None)):
            result = _process_url("https://vimeo.com/1084537")

        assert "error" not in result
        assert_video_html(result["embed_html"], video_url="https://player.vimeo.com/progressive_redirect/1084537/1080p.mp4", ar_w=16, ar_h=9)
        assert result["metadata"]["title"] == "Big Buck Bunny"


# ─── Tests: HLS (Dailymotion) ────────────────────────────────────────────

class TestHlsPath:
    def test_returns_hls_video_html(self, hls_only_data):
        with patch("video_embedder._run_ytdlp", return_value=(hls_only_data, None)):
            result = _process_url("https://www.dailymotion.com/video/x9yfz8u")

        assert "error" not in result
        assert_video_html(
            result["embed_html"],
            video_url="https://vod3.cf.dmcdn.net/sec2(x9yfz8u_1080)/video.m3u8", is_hls=True,
            ar_w=16, ar_h=9,
        )
        assert result["metadata"]["title"] == "Big Buck Bunny | Official Blender Foundation Short Film (HD, 60fps)"


# ─── Tests: webm (Dailymotion) ───────────────────────────────────────────

class TestWebmPath:
    def test_returns_video_html(self, direct_webm_data):
        with patch("video_embedder._run_ytdlp", return_value=(direct_webm_data, None)):
            result = _process_url("https://www.dailymotion.com/video/x24fho2")

        assert "error" not in result
        # Picks HLS (720p) over webm (360p) — higher resolution wins
        assert_video_html(
            result["embed_html"],
            video_url="https://vod3.cf.dmcdn.net/sec2(x24fho2_720)/video.m3u8", is_hls=True,
            ar_w=16, ar_h=9,
        )
        assert result["metadata"]["title"] == "Big Buck Bunny - Blender Foundation"


# ─── Tests: no usable formats ────────────────────────────────────────────

class TestNoUsableFormats:
    def test_returns_empty_embed_html(self, no_usable_formats_data):
        with patch("video_embedder._run_ytdlp", return_value=(no_usable_formats_data, None)):
            result = _process_url("https://example.com/weird987")

        assert "error" not in result
        assert result["embed_html"] == ""


# ─── Tests: yt-dlp error ────────────────────────────────────────────────

class TestErrorPath:
    def test_returns_error(self):
        with patch("video_embedder._run_ytdlp", return_value=(None, "HTTP Error 410: Gone")):
            result = _process_url("https://example.com/broken")

        assert "error" in result
        assert "410" in result["error"]
