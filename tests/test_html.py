"""Tests for HTML builders — pure HTML generation, no network."""

import pytest

from video_embedder import (
    _build_iframe_html,
    _build_video_html,
    _build_embed_code,
)


class TestBuildIframeHtml:
    def test_basic(self):
        html = _build_iframe_html("https://example.com/embed/abc123")
        assert "iframe" in html
        assert "https://example.com/embed/abc123" in html
        assert "aspect-ratio:16/9" in html
        assert "max-width:calc(100vh*16/9)" in html
        assert "width:100vw" in html

    def test_title_escaping(self):
        html = _build_iframe_html("https://x.com/e", title='He said "hello"')
        assert "iframe" in html
        assert "&quot;hello&quot;" in html
        assert '"hello"' not in html

    def test_empty_title(self):
        html = _build_iframe_html("https://x.com/e")
        assert "iframe" in html


class TestBuildVideoHtml:
    def test_mp4(self):
        html = _build_video_html("https://cdn.example.com/video.mp4")
        assert "video" in html
        assert "https://cdn.example.com/video.mp4" in html
        assert "controls" in html
        assert "width:100vw" in html
        assert "max-height:calc(100vw*9/16)" in html

    def test_hls(self):
        html = _build_video_html("https://cdn.example.com/stream.m3u8", m3u8=True)
        assert "video" in html
        assert "https://cdn.example.com/stream.m3u8" in html
        assert "controls" in html
        assert "width:100vw" in html

    def test_playsinline_on_mp4(self):
        html = _build_video_html("https://example.com/v.mp4")
        assert "playsinline" in html


class TestBuildEmbedCode:
    def test_wraps_in_html_code_block(self):
        result = _build_embed_code('<body style="margin:0"><div>content</div></body>')
        assert "Output this HTML exactly" in result
        assert "```html" in result
        assert "<body" in result
        assert "```" in result
