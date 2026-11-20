# GTA VI Auto-Clipper Pro — Cloud + Android Dashboard (v2.2.0)

This build is designed so an Android phone is the **control device**, while the cloud container performs YouTube fetching, FFmpeg rendering, transcription/metadata calls, and queue processing. Do not attempt to run FFmpeg video jobs on the phone.

## What this build does

- Responsive dashboard served by the same FastAPI origin (no localhost URL assumptions).
- Live public-chat monitoring and chat-velocity spike detection.
- SQLite-backed job/clip/event records, with pending/processing jobs recovered after a service restart.
- VOD clip requests and 9:16 FFmpeg rendering.
- Configurable higher-quality H.264 encoding: `medium` preset, CRF 18 by default, AAC 192 kbps.
- Optional Gemini metadata and Groq Whisper word-timestamp captions.
- API-key protection for API endpoints, WebSocket key check, and basic per-IP rate limiting.
- Persistent-volume support for the database, rendered clips, temp files, and YouTube token.

## Important feature boundaries — read before deploying

- Live chat spikes currently trigger capture **from the detection moment**. A true rolling pre-roll/post-roll video buffer is still not implemented; footage before detection cannot be recovered.
- Spike confidence is chat-only. Audio/visual event detection is not implemented.
- The included YouTube OAuth helper still uses a local-server OAuth flow. That is not suitable for unattended cloud/mobile OAuth yet. Keep auto-upload off until a proper web OAuth callback flow is configured.
- The queue is persisted as job records in SQLite and re-queued on process startup. It is a single-container/single-instance design; do not scale to multiple replicas without moving to a shared queue/database and distributed locking.
- YouTube download availability and use are subject to YouTube terms, access restrictions, and rights. Only process content you own or are authorized to use.

## Deploy from an Android phone using Render

You do not need a PC, but you do need a GitHub repository because Render deploys this Docker project from source control.

1. On your phone, open GitHub in Chrome and sign in.
2. Create a **private** repository, for example `gta-vi-auto-clipper-pro`.
3. Upload the extracted project files from this ZIP into the repository. Keep the root files (`Dockerfile`, `render.yaml`, `.dockerignore`) at repository root.
4. Open Render in Chrome, choose **New → Blueprint**, connect GitHub, and select this repository.
5. Review the Blueprint. It creates one Docker web service and a 20 GB persistent disk mounted at `/var/data`.
6. Deploy. First build can take several minutes because it installs FFmpeg and builds the React dashboard.
7. In Render service → Environment, add `GEMINI_API_KEY` and `GROQ_API_KEY` if you want those optional features. Never put API keys in frontend code or GitHub.
8. Find the generated `API_AUTH_KEY` in the service environment settings. Open the deployed service URL on Android Chrome and paste that key into the dashboard's Cloud access key field.
9. Keep the Render service running while jobs are processing. A sleeping/stopped service cannot monitor streams or render clips.

**Cost note:** this blueprint uses a paid web-service plan and a persistent disk because video processing needs dependable CPU/RAM and persistent storage. Free hosting tiers commonly sleep, have no persistent disk, or impose resource limits; they are not a reliable production video-rendering environment. Check the provider's current price before confirming deployment. A 20 GB disk is not a promise of unlimited clip retention.

## Local development (PC only)

Python 3.11+, Node 20+, and FFmpeg are required. Install backend requirements, run `uvicorn backend.main:app`, then build/run the Vite frontend. Cloud deployment does not require these tools on your phone.

## Environment variables

See `backend/.env.example`. In cloud, set `CLIPPER_DATA_DIR=/var/data`, `HOST=0.0.0.0`, and a strong random `API_AUTH_KEY`. Keep `MAX_CONCURRENT_JOBS=1` initially. The default `FFMPEG_PRESET=medium`, `FFMPEG_CRF=18`, and `CAPTURE_CRF=18` favor visual quality over speed; cloud CPU capacity determines render time.

## Tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q backend
```

## Storage paths

- SQLite: `$CLIPPER_DATA_DIR/gta_clipper.db`
- Rendered clips: `$CLIPPER_DATA_DIR/clips/`
- Temporary work: `$CLIPPER_DATA_DIR/temp/`
- YouTube token: `$CLIPPER_DATA_DIR/youtube_token.json`
