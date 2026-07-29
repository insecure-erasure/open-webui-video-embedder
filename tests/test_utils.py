"""Tests for utility functions — pure, no network."""

import pytest

from video_embedder import _format_duration, _get_best_format, _get_best_direct_mp4


# ── _format_duration ──────────────────────────────────────────────────────

class TestFormatDuration:
    def test_seconds_only(self):
        assert _format_duration(0) == "0:00"
        assert _format_duration(45) == "0:45"
        assert _format_duration(59) == "0:59"

    def test_minutes(self):
        assert _format_duration(60) == "1:00"
        assert _format_duration(90) == "1:30"
        assert _format_duration(3599) == "59:59"

    def test_hours(self):
        assert _format_duration(3600) == "1:00:00"
        assert _format_duration(3661) == "1:01:01"
        assert _format_duration(7384) == "2:03:04"


# ── Format selection ──────────────────────────────────────────────────────

class TestGetBestFormat:
    def test_prefers_highest_resolution(self):
        formats = [
            {"ext": "mp4", "protocol": "https", "height": 720},
            {"ext": "mp4", "protocol": "https", "height": 1080},
        ]
        result = _get_best_format({"formats": formats})
        assert result["height"] == 1080

    def test_skips_mhtml(self):
        formats = [
            {"ext": "mhtml", "protocol": "mhtml", "height": 9999},
            {"ext": "mp4", "protocol": "https", "height": 720},
        ]
        result = _get_best_format({"formats": formats})
        assert result["ext"] == "mp4"

    def test_prefers_mp4_over_hls_at_same_height(self):
        formats = [
            {"ext": "mp4", "protocol": "https", "height": 1080},
            {"ext": "ts", "protocol": "m3u8", "height": 1080, "url": "..."},
        ]
        result = _get_best_format({"formats": formats})
        assert result["ext"] == "mp4"
        assert result["protocol"] == "https"

    def test_no_formats(self):
        assert _get_best_format({"formats": []}) is None


class TestGetBestDirectMp4:
    def test_picks_largest_mp4(self):
        formats = [
            {"ext": "mp4", "protocol": "https", "height": 720, "url": "720.mp4"},
            {"ext": "mp4", "protocol": "https", "height": 1080, "url": "1080.mp4"},
        ]
        assert _get_best_direct_mp4({"formats": formats}) == "1080.mp4"

    def test_ignores_non_https_or_non_mp4(self):
        formats = [
            {"ext": "webm", "protocol": "https", "height": 1080, "url": "vid.webm"},
            {"ext": "mp4", "protocol": "m3u8", "height": 720, "url": "hls.mp4"},
            {"ext": "mp4", "protocol": "https", "height": 480, "url": "480.mp4"},
        ]
        assert _get_best_direct_mp4({"formats": formats}) == "480.mp4"

    def test_no_mp4_https(self):
        formats = [
            {"ext": "webm", "protocol": "https", "height": 1080},
            {"ext": "mp4", "protocol": "m3u8"},
        ]
        assert _get_best_direct_mp4({"formats": formats}) is None
