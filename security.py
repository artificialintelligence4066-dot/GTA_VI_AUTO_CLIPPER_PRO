import re
from urllib.parse import urlparse

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"}

def extract_video_id_safe(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("A valid YouTube URL is required")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in YOUTUBE_HOSTS:
        raise ValueError("Only YouTube URLs are supported")
    host = (parsed.hostname or "").lower()
    candidate = ""
    if host.endswith("youtu.be"):
        candidate = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        from urllib.parse import parse_qs
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    else:
        match = re.match(r"^/(?:live|shorts|embed)/([A-Za-z0-9_-]{6,20})", parsed.path)
        candidate = match.group(1) if match else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", candidate or ""):
        raise ValueError("Could not extract a valid YouTube video ID")
    return candidate
