# Templates

HTML fragments used by the Video Embedder tool to render embedded players.

## Available templates

| File | Used for | Placeholders |
|---|---|---|
| `iframe.html` | Sites that require their own iframe (RedGIFs, xHamster, PornHub, XVideos, YouTube, etc.) | `{embed_url}`, `{safe_title}` |
| `video.html` | Direct MP4 streams from any other site | `{video_url}` |
| `hls.html` | HLS streams (m3u8) from any other site | `{video_url}` |

## Customisation

These templates are loaded at runtime via `_load_template()` in `video_embedder.py`.
If a file doesn't exist, the tool falls back to the inline default — so you can
safely delete any template you don't need to customise.

All wrappers use `padding-bottom:56.25%` for a consistent 16:9 aspect ratio.
