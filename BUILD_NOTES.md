# Build Notes — Cloud/Android upgrade v2.2.0

## Changes in this upgrade
- Added Docker multi-stage build: Node builds the React/Vite dashboard; Python runtime includes FFmpeg and serves the dashboard from FastAPI.
- Added Render Blueprint with a paid web service, health check, generated API key, and persistent 20 GB volume.
- Moved SQLite, clips, temporary media, and YouTube token storage under `CLIPPER_DATA_DIR` so they can survive container restarts when backed by a persistent volume.
- Changed frontend API/WebSocket URLs to same-origin defaults; removed hard-coded localhost clip links.
- Added touch-first CSS and partial dashboard loading so one optional endpoint failure does not blank every section.
- Changed default H.264 encoding from ultrafast/CRF 23–24 to medium/CRF 18 and AAC 192 kbps; values are configurable.
- Updated health endpoint to expose active render profile and data path.

## Not represented as completed
- True live rolling pre-roll/post-roll capture is still not implemented.
- Audio/visual spike detection is not implemented.
- YouTube OAuth still needs a cloud-compatible web callback before auto-upload can be considered ready.
- The service is designed for one replica; a distributed multi-worker queue is not included.

## Deployment assumptions
- Render Blueprint deployment from a GitHub repository.
- Paid compute + persistent disk; free tier is not a dependable video-processing target.
- API key must be pasted into the dashboard on each new browser session; the frontend intentionally does not persist it in localStorage.
