#!/usr/bin/env python3
"""Dump the Rich UI player document to a file for the node JS tests.

Usage: python3 tests/dump_player_html.py <output.html>

The document is built by the real tool code (video_embedder._build_player_document)
so the node tests exercise the exact script that ships in production.
"""

import sys

from video_embedder import _build_iframe_html, _build_player_document, _build_video_html

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/player.html"


def main() -> None:
    players = [
        _build_video_html("https://cdn.example.com/video.mp4", width=1920, height=1080),
        _build_iframe_html("https://www.youtube.com/embed/abc123", title='Test "vid"', width=1920, height=1080),
        _build_video_html("https://cdn.example.com/portrait.mp4", width=1080, height=1920),
    ]
    doc = _build_player_document(players)
    with open(OUT, "w") as f:
        f.write(doc)
    print(f"wrote {len(doc)} bytes to {OUT}")


if __name__ == "__main__":
    main()
