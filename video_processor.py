import subprocess
from pathlib import Path
from typing import Optional
from .security import extract_video_id_safe
from . import config


def _run(command, timeout=900):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)


def download_segment(video_url: str, output_raw: Path, duration: int = 30, is_live: bool = True, start_sec: Optional[int] = None) -> Path:
    extract_video_id_safe(video_url)
    output_raw.parent.mkdir(parents=True, exist_ok=True)
    # Resolve a single media URL via yt-dlp. URL validation above prevents arbitrary-site fetching.
    result = _run(["yt-dlp", "--no-warnings", "--no-playlist", "-f", "best[height<=1080]/best", "-g", video_url], timeout=90)
    stream_url = next((line.strip() for line in result.stdout.splitlines() if line.strip().startswith(("http://", "https://"))), None)
    if not stream_url:
        raise RuntimeError("yt-dlp did not return a media stream URL")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if not is_live and start_sec is not None:
        cmd += ["-ss", str(max(0, int(start_sec)))]
    cmd += ["-i", stream_url, "-t", str(max(5, min(180, int(duration)))), "-threads", str(config.FFMPEG_THREADS), "-c:v", "libx264", "-preset", config.FFMPEG_PRESET, "-crf", str(config.CAPTURE_CRF), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output_raw)]
    _run(cmd, timeout=max(180, duration * 12))
    if not output_raw.exists() or output_raw.stat().st_size < 1024:
        raise RuntimeError("FFmpeg did not create a valid clip")
    return output_raw


def render_vertical_short(raw_video: Path, output_final: Path, streamer_credit: str = "@Streamer", ass_subtitle_path: Optional[Path] = None, layout_mode: str = "blur_zoom") -> Path:
    output_final.parent.mkdir(parents=True, exist_ok=True)
    credit = (streamer_credit or "@Streamer").replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")
    draw = f"drawtext=text='Credit\\: {credit}':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.55:boxborderw=12:x=(w-text_w)/2:y=90"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_video)]
    if layout_mode == "center_crop":
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920," + draw
        if ass_subtitle_path and ass_subtitle_path.exists():
            ass = str(ass_subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            vf += f",ass='{ass}'"
        cmd += ["-vf", vf]
    else:
        graph = "[0:v]split=2[bgsrc][fgsrc];[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:6[bg];[fgsrc]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[base];[base]" + draw
        if ass_subtitle_path and ass_subtitle_path.exists():
            ass = str(ass_subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            graph += f",ass='{ass}'"
        graph += "[vout]"
        cmd += ["-filter_complex", graph, "-map", "[vout]", "-map", "0:a?"]
    cmd += ["-threads", str(config.FFMPEG_THREADS), "-c:v", "libx264", "-preset", config.FFMPEG_PRESET, "-crf", str(config.FFMPEG_CRF), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output_final)]
    _run(cmd, timeout=1200)
    if not output_final.exists() or output_final.stat().st_size < 1024:
        raise RuntimeError("FFmpeg render failed to create output")
    return output_final
