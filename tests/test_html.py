"""Tests for HTML builders — pure HTML generation, no network."""

import pytest

from video_embedder import (
    _build_iframe_html,
    _build_video_html,
    _build_player_document,
)


class TestBuildIframeHtml:
    def test_basic(self):
        html = _build_iframe_html("https://example.com/embed/abc123")
        assert 'class="player"' in html
        assert 'data-ar="16/9"' in html
        assert "iframe" in html
        assert 'src="https://example.com/embed/abc123"' in html
        assert "allowfullscreen" in html

    def test_title_escaping(self):
        html = _build_iframe_html("https://x.com/e", title='He said "hello" & bye')
        assert "iframe" in html
        assert "&quot;hello&quot;" in html
        assert 'title="He said "hello"' not in html

    def test_empty_title(self):
        html = _build_iframe_html("https://x.com/e")
        assert "iframe" in html
        assert 'title=""' in html

    def test_aspect_ratio_from_dimensions(self):
        html = _build_iframe_html("https://x.com/e", width=1080, height=1920)
        assert 'data-ar="9/16"' in html


class TestBuildVideoHtml:
    def test_mp4(self):
        html = _build_video_html("https://cdn.example.com/video.mp4")
        assert 'class="player"' in html
        assert "video" in html
        assert 'src="https://cdn.example.com/video.mp4"' in html
        assert "controls" in html
        assert "autoplay" in html
        assert "muted" in html
        assert "playsinline" in html

    def test_hls(self):
        html = _build_video_html("https://cdn.example.com/stream.m3u8")
        assert "video" in html
        assert 'src="https://cdn.example.com/stream.m3u8"' in html
        assert "controls" in html

    def test_url_escaping(self):
        html = _build_video_html("https://x.com/v?file=a&b=c")
        assert 'src="https://x.com/v?file=a&amp;b=c"' in html

    def test_aspect_ratio_from_dimensions(self):
        html = _build_video_html("https://x.com/v.mp4", width=1280, height=720)
        assert 'data-ar="16/9"' in html


class TestBuildPlayerDocument:
    def test_single_player_document(self):
        player = _build_video_html("https://x.com/v.mp4")
        doc = _build_player_document([player])
        assert doc.startswith("<!DOCTYPE html>")
        assert player in doc
        assert "reportHeight" in doc
        assert "loadedmetadata" in doc
        assert "screen.availHeight" in doc
        assert "iframe:height" in doc
        assert "ResizeObserver" in doc
        assert "overflow:hidden" in doc

    def test_multiple_players_combined(self):
        p1 = _build_video_html("https://x.com/1.mp4")
        p2 = _build_iframe_html("https://y.com/embed/2")
        doc = _build_player_document([p1, p2])
        assert p1 in doc
        assert p2 in doc
        assert doc.count('class="player"') == 2
        assert doc.count("<video") == 1
        assert doc.count("<iframe") == 1
