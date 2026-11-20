import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from . import config


def extract_audio(video_path: Path, audio_path: Path) -> Path:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        str(audio_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return audio_path


def format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass_subtitles(words: List[Dict], output_ass: Path, words_per_group: int = 3) -> Path:
    header = """[Script Info]
Title: GTA VI Auto Clipper Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,76,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    for i in range(0, len(words), words_per_group):
        chunk = words[i:i + words_per_group]
        if not chunk:
            continue
        start_t = format_ass_time(chunk[0]["start"])
        end_t = format_ass_time(chunk[-1]["end"])
        text = " ".join(w["word"].strip().upper() for w in chunk)
        text = text.replace("{", "").replace("}", "")
        lines.append(f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{text}\n")

    output_ass.write_text("".join(lines), encoding="utf-8")
    return output_ass


def transcribe_clip(video_path: Path, clip_id: str) -> Tuple[str, Optional[Path]]:
    if not config.GROQ_API_KEY:
        return ("", None)

    audio_path = config.TEMP_DIR / f"{clip_id}.wav"
    ass_path = config.TEMP_DIR / f"{clip_id}.ass"

    try:
        extract_audio(video_path, audio_path)
        from groq import Groq
        client = Groq(api_key=config.GROQ_API_KEY)

        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(audio_path.name, audio_file.read()),
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )

        full_text = getattr(transcription, "text", "") or ""
        raw_words = getattr(transcription, "words", None) or []

        words = []
        for w in raw_words:
            if isinstance(w, dict):
                words.append({"word": w.get("word", ""), "start": float(w.get("start", 0)), "end": float(w.get("end", 0))})
            else:
                words.append({"word": getattr(w, "word", ""), "start": float(getattr(w, "start", 0)), "end": float(getattr(w, "end", 0))})

        if words:
            build_ass_subtitles(words, ass_path)
            return full_text.strip(), ass_path

        return full_text.strip(), None
    except Exception as e:
        print(f"[Transcriber Warning] {e}")
        return ("", None)
    finally:
        if audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                pass
