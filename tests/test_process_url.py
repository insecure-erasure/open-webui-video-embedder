"""Tests for _process_url with mocked yt-dlp — simulates every code path.

Covers all embedding methods:
  - Iframe path  (known extractor in EMBED_MAP)
  - Direct MP4   (generic site with direct MP4 format)
  - HLS stream   (generic site with only HLS/m3u8)
  - Direct URL   (generic site with no formats, uses yt-dlp's top-level url)
  - Fallback     (generic site with no usable formats at all)
  - Error        (yt-dlp returns None)
"""

from unittest.mock import patch

import pytest

from video_embedder import _process_url


# ─── Fixtures: mock yt-dlp responses ──────────────────────────────────────

@pytest.fixture
def iframe_data():
    """Simulates yt-dlp output for a known iframe site (RedGifs)."""
    return {
        "id": "amusingcat",
        "extractor": "RedGifs",
        "title": "Cat being funny",
        "webpage_url": "https://www.redgifs.com/watch/amusingcat",
        "url": "https://cdn.redgifs.com/amusingcat.mp4",
        "duration": 42,
        "view_count": 12345,
        "uploader": "CatLover",
        "width": 1920,
        "height": 1080,
        "formats": [
            {"ext": "mp4", "protocol": "https", "height": 720, "url": "https://cdn.redgifs.com/amusingcat_720.mp4"},
            {"ext": "mp4", "protocol": "https", "height": 1080, "url": "https://cdn.redgifs.com/amusingcat_1080.mp4"},
        ],
    }


@pytest.fixture
def direct_mp4_data():
    """Simulates yt-dlp output for a generic site with direct MP4."""
    return {
        "id": "tutorial123",
        "extractor": "vimeo",
        "title": "How to build a birdhouse",
        "webpage_url": "https://vimeo.com/123456789",
        "url": "https://vod.vimeo.com/tutorial123.mp4",
        "duration": 634,
        "view_count": 54321,
        "uploader": "DIY Channel",
        "width": 1920,
        "height": 1080,
        "formats": [
            {"ext": "mp4", "protocol": "https", "height": 720, "url": "https://vod.vimeo.com/tutorial123_720.mp4"},
            {"ext": "mp4", "protocol": "https", "height": 1080, "url": "https://vod.vimeo.com/tutorial123_1080.mp4"},
            {"ext": "mp4", "protocol": "m3u8_native", "height": 1080, "url": "https://vod.vimeo.com/tutorial123.m3u8"},
        ],
    }


@pytest.fixture
def hls_only_data():
    """Simulates yt-dlp output for a site that only offers HLS."""
    return {
        "id": "livestream789",
        "extractor": "twitch",
        "title": "Live coding session",
        "webpage_url": "https://twitch.tv/streamer789",
        "url": "https://video.twitch.tv/livestream789.m3u8",
        "duration": 3661,
        "view_count": 999,
        "uploader": "Streamer789",
        "width": 1280,
        "height": 720,
        "formats": [
            {"ext": "ts", "protocol": "m3u8", "height": 720, "url": "https://video.twitch.tv/livestream789_720.m3u8"},
            {"ext": "ts", "protocol": "m3u8", "height": 480, "url": "https://video.twitch.tv/livestream789_480.m3u8"},
        ],
    }


@pytest.fixture
def direct_webm_data():
    """Simulates yt-dlp output where best format is non-MP4 (webm) with a direct URL."""
    return {
        "id": "clip456",
        "extractor": "dailymotion",
        "title": "Funny dog compilation",
        "webpage_url": "https://dailymotion.com/video/clip456",
        "url": "https://www.dailymotion.com/cdn/clip456.webm",
        "duration": 185,
        "view_count": 78901,
        "uploader": "DogVideos",
        "width": 640,
        "height": 360,
        "formats": [
            {"ext": "webm", "protocol": "https", "height": 360, "url": "https://www.dailymotion.com/cdn/clip456.webm"},
        ],
    }


@pytest.fixture
def no_formats_data():
    """Simulates yt-dlp output with no usable formats at all."""
    return {
        "id": "weird987",
        "extractor": "generic",
        "title": "Some obscure stream",
        "webpage_url": "https://example.com/weird987",
        "url": None,
        "duration": None,
        "view_count": None,
        "uploader": None,
        "width": None,
        "height": None,
        "formats": [
            {"ext": "mhtml", "protocol": "mhtml", "height": 9999},
        ],
    }


# ─── Helpers ──────────────────────────────────────────────────────────────

def assert_iframe_html(html: str, *, embed_url: str, title: str):
    """Assert html is a valid iframe embed."""
    assert "iframe" in html, f"Expected iframe in output, got:\n{html}"
    assert embed_url in html, f"Expected {embed_url} in output"
    assert 'allowfullscreen' in html
    assert "56.25%" in html  # aspect ratio


def assert_video_html(html: str, *, video_url: str, is_hls: bool = False):
    """Assert html is a valid <video> embed."""
    assert "video" in html, f"Expected <video> in output, got:\n{html}"
    assert "controls" in html
    assert video_url in html, f"Expected {video_url} in output"
    assert "56.25%" in html
    if is_hls:
        assert "application/x-mpegURL" in html


def assert_metadata_in(output: str, *, extractor: str, title: str, duration: str):
    """Assert that metadata fields appear in the formatted output."""
    assert title in output, f"Expected title '{title}' in output"
    assert duration in output, f"Expected duration '{duration}' in output"
    assert extractor in output, f"Expected extractor '{extractor}' in output"


# ─── Tests: iframe path ──────────────────────────────────────────────────

class TestIframePath:
    """Known site in EMBED_MAP → should generate iframe HTML."""

    def test_returns_iframe_html(self, iframe_data):
        with patch("video_embedder._run_ytdlp", return_value=iframe_data):
            result = _process_url("https://www.redgifs.com/watch/amusingcat")

        assert "error" not in result
        assert_html = result["embed_html"]
        meta = result["metadata"]

        assert_iframe_html(
            assert_html,
            embed_url="https://www.redgifs.com/ifr/amusingcat",
            title="Cat being funny",
        )
        assert meta["extractor"] == "RedGifs"
        assert meta["stream_url"] == "https://cdn.redgifs.com/amusingcat_1080.mp4"

    def test_metadata_has_all_fields(self, iframe_data):
        with patch("video_embedder._run_ytdlp", return_value=iframe_data):
            result = _process_url("https://www.redgifs.com/watch/amusingcat")

        meta = result["metadata"]
        assert meta["title"] == "Cat being funny"
        assert meta["duration"] == "0:42"
        assert meta["uploader"] == "CatLover"
        assert meta["view_count"] == "12.3K"
        assert meta["resolution"] == "1920×1080"
        assert meta["id"] == "amusingcat"

    def test_formatted_output(self, iframe_data):
        with patch("video_embedder._run_ytdlp", return_value=iframe_data):
            result = _process_url("https://www.redgifs.com/watch/amusingcat")

        from video_embedder import _format_single_result
        output = _format_single_result(result)

        assert_metadata_in(
            output,
            extractor="RedGifs",
            title="Cat being funny",
            duration="0:42",
        )
        # Original link and stream link, not raw HTML
        assert "redgifs.com/watch/amusingcat" in output
        assert "Stream" in output
        assert "<iframe" not in output


# ─── Tests: direct MP4 path (generic site) ────────────────────────────────

class TestDirectMp4Path:
    """Generic site with direct HTTPS MP4 → <video> tag."""

    def test_returns_video_html(self, direct_mp4_data):
        with patch("video_embedder._run_ytdlp", return_value=direct_mp4_data):
            result = _process_url("https://vimeo.com/123456789")

        assert "error" not in result
        assert_video_html(
            result["embed_html"],
            video_url="https://vod.vimeo.com/tutorial123_1080.mp4",
        )
        assert result["metadata"]["extractor"] == "vimeo"

    def test_metadata(self, direct_mp4_data):
        with patch("video_embedder._run_ytdlp", return_value=direct_mp4_data):
            result = _process_url("https://vimeo.com/123456789")

        meta = result["metadata"]
        assert meta["duration"] == "10:34"
        assert meta["uploader"] == "DIY Channel"
        assert meta["view_count"] == "54.3K"
        assert meta["resolution"] == "1920×1080"

    def test_formatted_output(self, direct_mp4_data):
        with patch("video_embedder._run_ytdlp", return_value=direct_mp4_data):
            result = _process_url("https://vimeo.com/123456789")

        from video_embedder import _format_single_result
        output = _format_single_result(result)

        assert_metadata_in(output, extractor="vimeo", title="How to build a birdhouse", duration="10:34")
        assert "vod.vimeo.com" in output
        # Direct MP4 sites should show the stream link
        assert "Stream" in output


# ─── Tests: HLS path (generic site) ──────────────────────────────────────

class TestHlsPath:
    """Generic site with only HLS streams → <video> with m3u8 source."""

    def test_returns_hls_video_html(self, hls_only_data):
        with patch("video_embedder._run_ytdlp", return_value=hls_only_data):
            result = _process_url("https://twitch.tv/streamer789")

        assert "error" not in result
        assert_video_html(
            result["embed_html"],
            video_url="https://video.twitch.tv/livestream789_720.m3u8",
            is_hls=True,
        )
        assert result["metadata"]["extractor"] == "twitch"

    def test_metadata(self, hls_only_data):
        with patch("video_embedder._run_ytdlp", return_value=hls_only_data):
            result = _process_url("https://twitch.tv/streamer789")

        meta = result["metadata"]
        assert meta["duration"] == "1:01:01"
        assert meta["uploader"] == "Streamer789"
        assert meta["view_count"] == "999"
        assert meta["resolution"] == "1280×720"

    def test_formatted_output(self, hls_only_data):
        with patch("video_embedder._run_ytdlp", return_value=hls_only_data):
            result = _process_url("https://twitch.tv/streamer789")

        from video_embedder import _format_single_result
        output = _format_single_result(result)

        assert_metadata_in(output, extractor="twitch", title="Live coding session", duration="1:01:01")
        assert "Stream" in output


# ─── Tests: non-MP4 direct URL (webm) ───────────────────────────────────

class TestNonMp4DirectUrl:
    """Generic site with no MP4 but a direct webm URL — <video> tag still works."""

    def test_returns_video_html(self, direct_webm_data):
        with patch("video_embedder._run_ytdlp", return_value=direct_webm_data):
            result = _process_url("https://dailymotion.com/video/clip456")

        assert "error" not in result
        assert_video_html(
            result["embed_html"],
            video_url="https://www.dailymotion.com/cdn/clip456.webm",
        )
        assert result["metadata"]["extractor"] == "dailymotion"


# ─── Tests: no usable formats → fallback link ────────────────────────────

class TestNoFormatsFallback:
    """Generic site with only mhtml format → cannot embed, shows link."""

    def test_fallback_to_webpage_link(self, no_formats_data):
        with patch("video_embedder._run_ytdlp", return_value=no_formats_data):
            result = _process_url("https://example.com/weird987")

        assert "error" not in result
        html = result["embed_html"]
        assert "Could not generate embed" in html
        assert "Open video on web" in html
        assert "example.com/weird987" in html
        assert result["metadata"]["extractor"] == "generic"

    def test_metadata_unknowns(self, no_formats_data):
        with patch("video_embedder._run_ytdlp", return_value=no_formats_data):
            result = _process_url("https://example.com/weird987")

        meta = result["metadata"]
        assert meta["duration"] == "?"
        assert meta["uploader"] == "?"
        assert meta["view_count"] == "?"
        assert meta["resolution"] == "?"


# ─── Tests: yt-dlp error ─────────────────────────────────────────────────

class TestErrorPath:
    """yt-dlp fails or returns None → error message."""

    def test_returns_error(self):
        with patch("video_embedder._run_ytdlp", return_value=None):
            result = _process_url("https://example.com/broken")

        assert "error" in result
        assert "Could not extract" in result["error"]

    def test_error_renders_properly(self):
        with patch("video_embedder._run_ytdlp", return_value=None):
            result = _process_url("https://example.com/broken")

        from video_embedder import _format_single_result
        output = _format_single_result(result)
        assert "Error" in output
        assert "Could not extract" in output
