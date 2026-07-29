"""Tests for _process_url with mocked yt-dlp — simulates every code path.

Covers:
  - Iframe path  (known extractor in EMBED_MAP)
  - Direct MP4   (generic site with direct MP4 format)
  - HLS stream   (generic site with only HLS/m3u8)
  - Webm direct  (generic site with webm format)
  - No embed     (only mhtml format -> no embed HTML)
  - Error        (yt-dlp returns None)
"""

from unittest.mock import patch

import pytest

from video_embedder import _process_url


# ─── Fixtures: mock yt-dlp responses ──────────────────────────────────────

@pytest.fixture
def iframe_data():
    return {
        "id": "ReflectingWellinformedGordonsetter",
        "extractor": "RedGifs",
        "title": "Mountain stream at sunrise",
        "webpage_url": "https://www.redgifs.com/watch/reflectingwellinformedgordonsetter",
        "url": "https://cdn.redgifs.com/reflectingwellinformedgordonsetter.mp4",
        "duration": 42,
        "view_count": 12345,
        "uploader": "nature_shots",
        "width": 1920,
        "height": 1080,
        "formats": [
            {"ext": "mp4", "protocol": "https", "height": 720, "url": "https://cdn.redgifs.com/reflectingwellinformedgordonsetter_720.mp4"},
            {"ext": "mp4", "protocol": "https", "height": 1080, "url": "https://cdn.redgifs.com/reflectingwellinformedgordonsetter_1080.mp4"},
        ],
    }


@pytest.fixture
def direct_mp4_data():
    return {
        "id": "tutorial123",
        "extractor": "vimeo",
        "title": "How to build a birdhouse",
        "webpage_url": "https://vimeo.com/123456789",
        "url": "https://vod.vimeo.com/tutorial123.mp4",
        "duration": 634,
        "formats": [
            {"ext": "mp4", "protocol": "https", "height": 720, "url": "https://vod.vimeo.com/tutorial123_720.mp4"},
            {"ext": "mp4", "protocol": "https", "height": 1080, "url": "https://vod.vimeo.com/tutorial123_1080.mp4"},
            {"ext": "mp4", "protocol": "m3u8_native", "height": 1080, "url": "https://vod.vimeo.com/tutorial123.m3u8"},
        ],
    }


@pytest.fixture
def hls_only_data():
    return {
        "id": "livestream789",
        "extractor": "twitch",
        "title": "Live coding session",
        "webpage_url": "https://twitch.tv/streamer789",
        "url": "https://video.twitch.tv/livestream789.m3u8",
        "duration": 3661,
        "formats": [
            {"ext": "ts", "protocol": "m3u8", "height": 720, "url": "https://video.twitch.tv/livestream789_720.m3u8"},
            {"ext": "ts", "protocol": "m3u8", "height": 480, "url": "https://video.twitch.tv/livestream789_480.m3u8"},
        ],
    }


@pytest.fixture
def direct_webm_data():
    return {
        "id": "clip456",
        "extractor": "dailymotion",
        "title": "Funny dog compilation",
        "webpage_url": "https://dailymotion.com/video/clip456",
        "url": "https://www.dailymotion.com/cdn/clip456.webm",
        "duration": 185,
        "formats": [
            {"ext": "webm", "protocol": "https", "height": 360, "url": "https://www.dailymotion.com/cdn/clip456.webm"},
        ],
    }


@pytest.fixture
def no_usable_formats_data():
    return {
        "id": "weird987",
        "extractor": "generic",
        "title": "Some obscure stream",
        "webpage_url": "https://example.com/weird987",
        "url": None,
        "duration": None,
        "formats": [
            {"ext": "mhtml", "protocol": "mhtml", "height": 9999},
        ],
    }


# ─── Helpers ──────────────────────────────────────────────────────────────

def assert_iframe_html(html: str, *, embed_url: str, title: str):
    assert "iframe" in html
    assert embed_url in html
    assert "width:100vw" in html
    assert "aspect-ratio:9/16" in html
    assert "max-width:calc((100vh*9)/16)" in html


def assert_video_html(html: str, *, video_url: str, is_hls: bool = False):
    assert "video" in html
    assert "controls" in html
    assert video_url in html
    assert "width:100vw" in html
    assert "max-height:calc((100vw*16)/9)" in html


# ─── Tests: iframe path ──────────────────────────────────────────────────

class TestIframePath:
    def test_returns_iframe_html(self, iframe_data):
        with patch("video_embedder._run_ytdlp", return_value=iframe_data):
            result = _process_url("https://www.redgifs.com/watch/reflectingwellinformedgordonsetter")

        assert "error" not in result
        assert_iframe_html(
            result["embed_html"],
            embed_url="https://www.redgifs.com/ifr/ReflectingWellinformedGordonsetter",
            title="Mountain stream at sunrise",
        )

    def test_metadata_has_title_and_urls(self, iframe_data):
        with patch("video_embedder._run_ytdlp", return_value=iframe_data):
            result = _process_url("https://www.redgifs.com/watch/reflectingwellinformedgordonsetter")

        meta = result["metadata"]
        assert meta["title"] == "Mountain stream at sunrise"
        assert meta["webpage_url"] == "https://www.redgifs.com/watch/reflectingwellinformedgordonsetter"
        assert meta["stream_url"] == "https://cdn.redgifs.com/reflectingwellinformedgordonsetter_1080.mp4"


# ─── Tests: direct MP4 path ──────────────────────────────────────────────

class TestDirectMp4Path:
    def test_returns_video_html(self, direct_mp4_data):
        with patch("video_embedder._run_ytdlp", return_value=direct_mp4_data):
            result = _process_url("https://vimeo.com/123456789")

        assert "error" not in result
        assert_video_html(
            result["embed_html"],
            video_url="https://vod.vimeo.com/tutorial123_1080.mp4",
        )
        assert result["metadata"]["title"] == "How to build a birdhouse"


# ─── Tests: HLS path ─────────────────────────────────────────────────────

class TestHlsPath:
    def test_returns_hls_video_html(self, hls_only_data):
        with patch("video_embedder._run_ytdlp", return_value=hls_only_data):
            result = _process_url("https://twitch.tv/streamer789")

        assert "error" not in result
        assert_video_html(
            result["embed_html"],
            video_url="https://video.twitch.tv/livestream789_720.m3u8",
            is_hls=True,
        )
        assert result["metadata"]["title"] == "Live coding session"


# ─── Tests: webm direct path ─────────────────────────────────────────────

class TestWebmPath:
    def test_returns_video_html(self, direct_webm_data):
        with patch("video_embedder._run_ytdlp", return_value=direct_webm_data):
            result = _process_url("https://dailymotion.com/video/clip456")

        assert "error" not in result
        assert_video_html(
            result["embed_html"],
            video_url="https://www.dailymotion.com/cdn/clip456.webm",
        )
        assert result["metadata"]["title"] == "Funny dog compilation"


# ─── Tests: no usable formats ────────────────────────────────────────────

class TestNoUsableFormats:
    def test_returns_empty_embed_html(self, no_usable_formats_data):
        with patch("video_embedder._run_ytdlp", return_value=no_usable_formats_data):
            result = _process_url("https://example.com/weird987")

        assert "error" not in result
        assert result["embed_html"] == ""


# ─── Tests: yt-dlp error ─────────────────────────────────────────────────

class TestErrorPath:
    def test_returns_error(self):
        with patch("video_embedder._run_ytdlp", return_value=None):
            result = _process_url("https://example.com/broken")

        assert "error" in result
        assert "Could not extract" in result["error"]
