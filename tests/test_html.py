"""Tests for HTML builders — pure HTML generation, no network."""

import pytest

from video_embedder import (
    _build_iframe_html,
    _build_video_html,
    _build_metadata_table,
    _build_link_row,
    _build_players_html,
    _build_context,
    _format_single_result,
)


# ── iframe ────────────────────────────────────────────────────────────────

class TestBuildIframeHtml:
    def test_basic(self):
        html = _build_iframe_html("https://example.com/embed/abc123")
        assert "iframe" in html
        assert "https://example.com/embed/abc123" in html
        assert "56.25%" in html  # aspect-ratio wrapper

    def test_title_escaping(self):
        html = _build_iframe_html("https://x.com/e", title='He said "hello"')
        assert "&quot;hello&quot;" in html
        assert '"hello"' not in html

    def test_empty_title(self):
        html = _build_iframe_html("https://x.com/e")
        assert "iframe" in html


# ── <video> tags ─────────────────────────────────────────────────────────

class TestBuildVideoHtml:
    def test_mp4(self):
        html = _build_video_html("https://cdn.example.com/video.mp4")
        assert "video" in html
        assert "https://cdn.example.com/video.mp4" in html
        assert 'type="video/mp4"' in html
        assert "56.25%" in html

    def test_hls(self):
        html = _build_video_html("https://cdn.example.com/stream.m3u8", m3u8=True)
        assert 'type="application/x-mpegURL"' in html
        assert "HLS" in html or "hls" in html

    def test_playsinline_on_mp4(self):
        html = _build_video_html("https://example.com/v.mp4")
        assert "playsinline" in html


# ── Metadata table ────────────────────────────────────────────────────────

class TestBuildMetadataTable:
    def test_all_fields(self):
        data = {
            "title": "My Video",
            "duration": "5:30",
            "uploader": "Creator",
            "view_count": "1.2K",
            "resolution": "1920×1080",
            "extractor": "vimeo",
        }
        table = _build_metadata_table(data)
        assert "My Video" in table
        assert "5:30" in table
        assert "Creator" in table
        assert "1.2K" in table
        assert "1920×1080" in table
        assert "vimeo" in table
        assert "|" in table  # markdown table separators

    def test_unknown_fields(self):
        data = {}
        table = _build_metadata_table(data)
        assert "?" in table


# ── Link row ──────────────────────────────────────────────────────────────

class TestBuildLinkRow:
    def test_both_links(self):
        row = _build_link_row(
            "https://vimeo.com/123",
            "https://cdn.example.com/video.mp4",
            "vimeo",
        )
        assert "Original" in row
        assert "vimeo.com/123" in row
        assert "Stream" in row

    def test_no_stream_url(self):
        row = _build_link_row("https://example.com/v", None, "generic")
        assert "Original" in row
        assert "Stream" not in row

    def test_no_webpage_url(self):
        row = _build_link_row("", "https://cdn.example.com/v.mp4", "generic")
        # Stream link is still shown even without an original page link
        assert "Stream" in row
        assert "cdn.example.com" in row


# ── Full result formatting (simulated Vimeo response) ─────────────────────

class TestFormatSingleResult:
    """Test _format_single_result with a simulated Vimeo video metadata."""

    @pytest.fixture
    def vimeo_result(self):
        return {
            "embed_html": _build_iframe_html(
                "https://player.vimeo.com/video/123456789",
                "Big Buck Bunny",
            ),
            "metadata": {
                "id": "123456789",
                "extractor": "vimeo",
                "title": "Big Buck Bunny",
                "duration": "10:34",
                "uploader": "Blender Foundation",
                "view_count": "42K",
                "resolution": "3840×2160",
                "webpage_url": "https://vimeo.com/123456789",
                "stream_url": None,
            },
        }

    def test_contains_title(self, vimeo_result):
        output = _format_single_result(vimeo_result)
        assert "Big Buck Bunny" in output

    def test_no_raw_html_in_text_output(self, vimeo_result):
        """_format_single_result now returns text-only metadata (HTML goes to rich embed)."""
        output = _format_single_result(vimeo_result)
        assert "iframe" not in output
        assert "<video" not in output

    def test_contains_metadata_table(self, vimeo_result):
        output = _format_single_result(vimeo_result)
        assert "10:34" in output
        assert "Blender Foundation" in output
        assert "42K" in output
        assert "3840×2160" in output

    def test_contains_original_link(self, vimeo_result):
        output = _format_single_result(vimeo_result)
        assert "vimeo.com/123456789" in output

    def test_error_result(self):
        output = _format_single_result({"error": "Something went wrong"})
        assert "Error" in output
        assert "Something went wrong" in output


# ── Players HTML (rich UI embed) ──────────────────────────────────────────

class TestBuildPlayersHtml:
    """Tests for _build_players_html — full HTML doc for rich UI embed."""

    def test_single_player(self):
        results = [
            {
                "embed_html": '<iframe src="https://example.com/embed/abc"></iframe>',
                "metadata": {},
            }
        ]
        html = _build_players_html(results)
        assert "<!DOCTYPE html>" in html
        assert "iframe" in html
        assert "example.com/embed/abc" in html
        assert 'parent.postMessage' in html
        assert "ResizeObserver" in html

    def test_multiple_players(self):
        results = [
            {"embed_html": '<iframe src="https://a.com/1"></iframe>', "metadata": {}},
            {"embed_html": '<iframe src="https://b.com/2"></iframe>', "metadata": {}},
        ]
        html = _build_players_html(results)
        assert "a.com/1" in html
        assert "b.com/2" in html
        assert html.index("a.com/1") < html.index("b.com/2")  # correct order

    def test_skips_errors(self):
        results = [
            {"error": "Failed"},
            {"embed_html": '<iframe src="https://ok.com/1"></iframe>', "metadata": {}},
        ]
        html = _build_players_html(results)
        assert "ok.com/1" in html
        # Error message must not bleed into player HTML
        assert "Failed" not in html

    def test_all_errors_returns_empty(self):
        results = [{"error": "Failed 1"}, {"error": "Failed 2"}]
        assert _build_players_html(results) == ""

    def test_empty_results(self):
        assert _build_players_html([]) == ""


# ── Build context (text for the LLM) ─────────────────────────────────────

class TestBuildContext:
    """Tests for _build_context — text summary for the LLM."""

    def test_single_video(self):
        results = [
            {
                "metadata": {
                    "title": "Big Buck Bunny",
                    "duration": "10:34",
                    "uploader": "Blender Foundation",
                    "view_count": "42K",
                    "resolution": "3840×2160",
                    "webpage_url": "https://vimeo.com/123",
                    "stream_url": "https://vod.vimeo.com/bbb.mp4",
                    "extractor": "vimeo",
                }
            }
        ]
        ctx = _build_context(results)
        assert "Video Embedder — 1 embedded" in ctx
        assert "Big Buck Bunny" in ctx
        assert "10:34" in ctx
        assert "Blender Foundation" in ctx
        assert "42K" in ctx
        assert "vimeo.com/123" in ctx
        assert "vod.vimeo.com" in ctx

    def test_multiple_videos(self):
        results = [
            {
                "metadata": {
                    "title": "Video One", "duration": "1:00",
                    "uploader": "U1", "view_count": "10",
                    "resolution": "1920×1080",
                    "webpage_url": "https://a.com/1",
                    "stream_url": None, "extractor": "siteA",
                }
            },
            {
                "metadata": {
                    "title": "Video Two", "duration": "2:00",
                    "uploader": "U2", "view_count": "20",
                    "resolution": "1280×720",
                    "webpage_url": "https://b.com/2",
                    "stream_url": "https://b.com/2.mp4", "extractor": "siteB",
                }
            },
        ]
        ctx = _build_context(results)
        assert "Video Embedder — 2 embedded" in ctx
        assert "Video 1" in ctx
        assert "Video 2" in ctx
        assert "Video One" in ctx
        assert "Video Two" in ctx
        assert "Stream:" in ctx

    def test_some_errors(self):
        results = [
            {"error": "Could not extract info"},
            {
                "metadata": {
                    "title": "Only this works", "duration": "0:30",
                    "uploader": "U", "view_count": "5",
                    "resolution": "640×360",
                    "webpage_url": "https://c.com/v",
                    "stream_url": None, "extractor": "generic",
                }
            },
        ]
        ctx = _build_context(results)
        assert "Video Embedder — 1 embedded, 1 failed" in ctx
        assert "Error" in ctx
        assert "Could not extract" in ctx
        assert "Only this works" in ctx

    def test_all_errors(self):
        results = [{"error": "Fail 1"}, {"error": "Fail 2"}]
        ctx = _build_context(results)
        assert "0 embedded, 2 failed" in ctx

    def test_empty(self):
        assert _build_context([]) == "Video Embedder — 0 embedded"
