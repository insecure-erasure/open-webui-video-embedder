"""Tests for utility functions — pure, no network."""

import pytest

from video_embedder import (
    _classify_http_error,
    _format_duration,
    _get_best_format,
    _get_best_direct_mp4,
    _get_youtube_id,
    _http_error_message,
)


# ── HTTP error classification ──────────────────────────────────────────────

from yt_dlp.networking.exceptions import HTTPError as _RealHTTPError


class _FakeResponse:
    """Minimal response object the real yt-dlp HTTPError reads .status from."""
    def __init__(self, status):
        self.status = status
        self.reason = "reason"


def _real_httperror(status):
    return _RealHTTPError(_FakeResponse(status))


class TestClassifyHttpError:
    def test_direct_httperror(self):
        assert _classify_http_error(_real_httperror(410)) == 410

    def test_wrapped_in_download_error(self):
        # yt-dlp wraps the HTTPError in a DownloadError (cause chain)
        outer = Exception("DownloadError")
        outer.__cause__ = _real_httperror(403)
        assert _classify_http_error(outer) == 403

    def test_nested_cause_chain(self):
        mid = Exception("mid")
        mid.__cause__ = _real_httperror(404)
        outer = Exception("outer")
        outer.__cause__ = mid
        assert _classify_http_error(outer) == 404

    def test_non_http_error(self):
        assert _classify_http_error(ValueError("boom")) is None

    def test_http_error_without_status(self):
        e = Exception("no status")
        e.__cause__ = _real_httperror(None)
        assert _classify_http_error(e) is None


class TestHttpErrorMessage:
    def test_known_codes(self):
        assert "410" in _http_error_message(410, "fallback")
        assert "removed" in _http_error_message(410, "fallback")
        assert "forbidden" in _http_error_message(403, "fallback")

    def test_unknown_code(self):
        assert "rejected" in _http_error_message(503, "fallback")
        assert "503" in _http_error_message(503, "fallback")

    def test_none_falls_back(self):
        assert _http_error_message(None, "raw message") == "raw message"


# ── _get_youtube_id ──────────────────────────────────────────────────────

class TestGetYoutubeId:
    def test_watch_url(self):
        assert _get_youtube_id("https://www.youtube.com/watch?v=hb5fsQyvFF4") == "hb5fsQyvFF4"

    def test_watch_url_with_extra_params(self):
        assert _get_youtube_id("https://www.youtube.com/watch?v=hb5fsQyvFF4&t=30s") == "hb5fsQyvFF4"

    def test_youtu_be_short(self):
        assert _get_youtube_id("https://youtu.be/hb5fsQyvFF4") == "hb5fsQyvFF4"

    def test_shorts(self):
        assert _get_youtube_id("https://www.youtube.com/shorts/hb5fsQyvFF4") == "hb5fsQyvFF4"

    def test_embed_url(self):
        assert _get_youtube_id("https://www.youtube.com/embed/hb5fsQyvFF4") == "hb5fsQyvFF4"

    def test_live_url(self):
        assert _get_youtube_id("https://www.youtube.com/live/hb5fsQyvFF4") == "hb5fsQyvFF4"

    def test_v_path(self):
        assert _get_youtube_id("https://www.youtube.com/v/hb5fsQyvFF4") == "hb5fsQyvFF4"

    def test_non_youtube(self):
        assert _get_youtube_id("https://vimeo.com/1084537") is None
        assert _get_youtube_id("https://example.com/watch?v=hb5fsQyvFF4") is None

    def test_invalid_id_length(self):
        assert _get_youtube_id("https://www.youtube.com/watch?v=tooshort") is None


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
