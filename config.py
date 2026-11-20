import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
# Cloud platforms should mount a persistent volume at CLIPPER_DATA_DIR.
DATA_DIR = Path(os.getenv("CLIPPER_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
CLIPS_DIR = DATA_DIR / "clips"
TEMP_DIR = DATA_DIR / "temp"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "gta_clipper.db"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
API_AUTH_KEY = os.getenv("API_AUTH_KEY", "").strip()
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
RATE_LIMIT_PER_MINUTE = max(10, int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")))
CLIP_DURATION_SECONDS = max(5, min(180, int(os.getenv("CLIP_DURATION_SECONDS", "30"))))
SPIKE_MULTIPLIER = max(1.1, float(os.getenv("SPIKE_MULTIPLIER", "2.5")))
MIN_MPM_THRESHOLD = max(1, int(os.getenv("MIN_MPM_THRESHOLD", "40")))
MIN_UNIQUE_AUTHORS = max(1, int(os.getenv("MIN_UNIQUE_AUTHORS", "5")))
CLIP_COOLDOWN_SECONDS = max(10, int(os.getenv("CLIP_COOLDOWN_SECONDS", "90")))
MAX_CONCURRENT_JOBS = max(1, min(2, int(os.getenv("MAX_CONCURRENT_JOBS", "1"))))
FFMPEG_THREADS = max(1, int(os.getenv("FFMPEG_THREADS", "2")))
FFMPEG_PRESET = os.getenv("FFMPEG_PRESET", "medium").strip()
FFMPEG_CRF = max(14, min(28, int(os.getenv("FFMPEG_CRF", "18"))))
CAPTURE_CRF = max(14, min(28, int(os.getenv("CAPTURE_CRF", "18"))))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
YOUTUBE_CLIENT_SECRETS = BASE_DIR / os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
YOUTUBE_TOKEN_FILE = DATA_DIR / "youtube_token.json"
