import asyncio
import re
import time
import uuid
from collections import deque
from typing import Callable, Awaitable, Dict, List, Optional, Tuple

from .security import extract_video_id_safe

HYPE_KEYWORDS = [
    "w", "ww", "www", "wwww", "clip", "clip that", "no way", "omg", "bro",
    "lmao", "lmaooo", "insane", "crazy", "gta", "gta6", "gta 6", "fire",
    "goat", "wtf", "bruh", "ayooo", "op", "gg", "legend", "sheesh",
    "bawal", "khatarnak", "bhai", "💀", "🔥", "😂", "🤯", "😱"
]


def normalize_message(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    return cleaned


def score_message_hype(text: str) -> float:
    lower = normalize_message(text)
    if not lower:
        return 0.0
    score = 1.0
    for kw in HYPE_KEYWORDS:
        if kw in lower:
            score += 0.55
    if text.strip().isupper() and len(text.strip()) >= 4:
        score += 0.45
    if "!" in lower or "?" in lower:
        score += 0.15
    return min(score, 3.5)


class ChatSpikeDetector:
    """
    Deterministic sliding-window chat velocity & hype spike detector with
    duplicate/spam filtering, unique-author floor, cooldown, and honest
    multi-modal confidence indicators (chat computed; audio/visual explicit null unless analyzed).
    """

    def __init__(
        self,
        spike_multiplier: float = 2.5,
        min_mpm: int = 40,
        min_unique_authors: int = 5,
        cooldown_seconds: int = 90,
        warmup_seconds: float = 20.0,
        author_spam_window: float = 2.5,
    ):
        self.spike_multiplier = spike_multiplier
        self.min_mpm = min_mpm
        self.min_unique_authors = min_unique_authors
        self.cooldown_seconds = cooldown_seconds
        self.warmup_seconds = warmup_seconds
        self.author_spam_window = author_spam_window

        self.start_time: Optional[float] = None
        self.last_spike_time: float = -1e9
        self.spam_filtered_total: int = 0

        # Entries: (timestamp, hype_score, author, raw_message, norm_message)
        self.window_10s: deque = deque()
        self.window_120s: deque = deque()
        self._author_last_seen: Dict[str, Tuple[float, str]] = {}

    def ingest_message(self, author: str, message: str, timestamp: Optional[float] = None) -> Dict:
        now = timestamp if timestamp is not None else time.time()
        if self.start_time is None:
            self.start_time = now

        norm = normalize_message(message)
        author_key = (author or "anon").strip().lower()

        # Spam & duplicate filter: ignore same user flooding within author_spam_window
        # or repeating identical message within 8 seconds
        last_seen = self._author_last_seen.get(author_key)
        if last_seen is not None:
            prev_ts, prev_norm = last_seen
            if norm == prev_norm and (now - prev_ts) < 8.0:
                self.spam_filtered_total += 1
                return {"accepted": False, "reason": "duplicate_message"}

        self._author_last_seen[author_key] = (now, norm)
        hype = score_message_hype(message)
        entry = (now, hype, author, message, norm)
        self.window_10s.append(entry)
        self.window_120s.append(entry)

        return {"accepted": True, "hype": hype, "is_hype": hype >= 1.55}

    def prune(self, now: float):
        while self.window_10s and now - self.window_10s[0][0] > 10.0:
            self.window_10s.popleft()
        while self.window_120s and now - self.window_120s[0][0] > 120.0:
            self.window_120s.popleft()
        # Keep author map bounded
        if len(self._author_last_seen) > 5000:
            cutoff = now - 30.0
            self._author_last_seen = {
                k: v for k, v in self._author_last_seen.items() if v[0] >= cutoff
            }

    def evaluate(self, now: Optional[float] = None) -> Dict:
        now = now if now is not None else time.time()
        if self.start_time is None:
            self.start_time = now

        self.prune(now)

        msg_count_10s = len(self.window_10s)
        current_mpm = msg_count_10s * 6.0
        current_hype_mpm = sum(e[1] for e in self.window_10s) * 6.0
        unique_authors = len({e[2].lower() for e in self.window_10s})

        elapsed = max(15.0, min(120.0, now - self.start_time))
        baseline_mpm = (len(self.window_120s) / elapsed) * 60.0
        baseline_hype_mpm = (sum(e[1] for e in self.window_120s) / elapsed) * 60.0

        spike_ratio = current_hype_mpm / max(baseline_hype_mpm, 12.0)

        # Compute Chat Confidence (0-100) honestly based on ratio, unique authors, and volume
        ratio_score = min(45.0, (spike_ratio / max(self.spike_multiplier, 0.5)) * 25.0)
        author_score = min(30.0, (unique_authors / max(self.min_unique_authors, 1)) * 18.0)
        volume_score = min(25.0, (current_mpm / max(self.min_mpm, 1)) * 15.0)
        chat_confidence = int(min(100, round(ratio_score + author_score + volume_score)))

        warmed_up = (now - self.start_time) >= self.warmup_seconds
        cooldown_ok = (now - self.last_spike_time) >= self.cooldown_seconds

        triggered = (
            warmed_up
            and cooldown_ok
            and current_mpm >= self.min_mpm
            and unique_authors >= self.min_unique_authors
            and spike_ratio >= self.spike_multiplier
        )

        if triggered:
            self.last_spike_time = now

        return {
            "triggered": triggered,
            "mpm": round(current_mpm, 1),
            "hype_mpm": round(current_hype_mpm, 1),
            "baseline_mpm": round(baseline_mpm, 1),
            "spike_ratio": round(spike_ratio, 2),
            "unique_authors": unique_authors,
            "spam_filtered_total": self.spam_filtered_total,
            "stream_elapsed_sec": round(now - self.start_time, 1),
            "confidence": {
                "chat": chat_confidence,
                "audio": None,
                "visual": None,
                "note": "Chat velocity & hype only; audio/visual analysis not performed in live chat monitor."
            },
            "top_chat": [f"{e[2]}: {e[3]}" for e in list(self.window_10s)[-25:]],
            "timestamp": now,
        }


class LiveChatMonitor:
    def __init__(
        self,
        video_url: str,
        on_telemetry: Callable[[dict], Awaitable[None]],
        on_spike: Callable[[dict], Awaitable[None]],
        spike_multiplier: float = 2.5,
        min_mpm: int = 40,
        min_unique_authors: int = 5,
        cooldown_seconds: int = 90,
    ):
        self.video_url = video_url
        self.video_id = extract_video_id_safe(video_url)
        self.on_telemetry = on_telemetry
        self.on_spike = on_spike
        self.detector = ChatSpikeDetector(
            spike_multiplier=spike_multiplier,
            min_mpm=min_mpm,
            min_unique_authors=min_unique_authors,
            cooldown_seconds=cooldown_seconds,
        )
        self.running = False
        self._chat = None

    def stop(self):
        self.running = False
        if self._chat is not None:
            try:
                self._chat.terminate()
            except Exception:
                pass

    async def start(self):
        self.running = True
        try:
            import pytchat
        except ImportError:
            await self.on_telemetry({
                "type": "log",
                "level": "error",
                "message": "pytchat is not installed. Run: pip install -r requirements.txt"
            })
            self.running = False
            return

        await self.on_telemetry({
            "type": "log",
            "level": "info",
            "message": f"Connecting to YouTube Live Chat ({self.video_id})..."
        })

        try:
            self._chat = await asyncio.to_thread(pytchat.create, video_id=self.video_id)
        except Exception as e:
            await self.on_telemetry({
                "type": "log",
                "level": "error",
                "message": f"Live chat connection failed (stream may be offline/VOD/chat disabled): {e}"
            })
            self.running = False
            return

        await self.on_telemetry({
            "type": "log",
            "level": "success",
            "message": "Live Chat connected. Spam filter & baseline warmup active (20s)."
        })

        last_emit = 0.0

        while self.running and self._chat.is_alive():
            try:
                data = await asyncio.to_thread(self._chat.get)
                now = time.time()
                accepted_recent = []

                for item in data.sync_items():
                    res = self.detector.ingest_message(item.author.name, item.message, timestamp=now)
                    if res["accepted"]:
                        accepted_recent.append({
                            "author": item.author.name,
                            "message": item.message,
                            "is_hype": res["is_hype"],
                        })

                metrics = self.detector.evaluate(now)

                if now - last_emit >= 1.0:
                    last_emit = now
                    await self.on_telemetry({
                        "type": "telemetry",
                        "mpm": metrics["mpm"],
                        "hype_mpm": metrics["hype_mpm"],
                        "baseline_mpm": metrics["baseline_mpm"],
                        "spike_ratio": metrics["spike_ratio"],
                        "unique_authors": metrics["unique_authors"],
                        "spam_filtered_total": metrics["spam_filtered_total"],
                        "stream_elapsed_sec": metrics["stream_elapsed_sec"],
                        "confidence": metrics["confidence"],
                        "messages": accepted_recent[-10:],
                        "timestamp": now,
                    })

                if metrics["triggered"]:
                    event_id = f"evt_{int(now)}_{uuid.uuid4().hex[:6]}"
                    await self.on_telemetry({
                        "type": "log",
                        "level": "spike",
                        "message": (
                            f"SPIKE DETECTED! {metrics['mpm']} MPM ({metrics['spike_ratio']}x baseline, "
                            f"{metrics['unique_authors']} unique users, chat confidence {metrics['confidence']['chat']}%)"
                        )
                    })
                    # Dispatch clip work without blocking chat polling/telemetry.
                    asyncio.create_task(self.on_spike({
                        "event_id": event_id,
                        "video_url": self.video_url,
                        "video_id": self.video_id,
                        "detected_at": now,
                        "stream_elapsed_sec": metrics["stream_elapsed_sec"],
                        "mpm": metrics["mpm"],
                        "baseline_mpm": metrics["baseline_mpm"],
                        "spike_ratio": metrics["spike_ratio"],
                        "unique_authors": metrics["unique_authors"],
                        "spam_filtered_count": metrics["spam_filtered_total"],
                        "confidence": metrics["confidence"],
                        "top_chat": metrics["top_chat"],
                        "is_live": True,
                    }))

                await asyncio.sleep(0.5)
            except Exception as e:
                await self.on_telemetry({
                    "type": "log",
                    "level": "error",
                    "message": f"Chat monitor error: {e}"
                })
                await asyncio.sleep(2.0)

        self.running = False
        await self.on_telemetry({
            "type": "log",
            "level": "info",
            "message": "Live chat monitoring stopped."
        })
