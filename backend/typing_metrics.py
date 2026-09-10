"""Privacy-safe typing telemetry.
Only numeric counts/timing are retained; actual key values are never stored.
"""
from collections import deque
import time

WINDOW_SECS = 10.0


class TypingMetrics:
    def __init__(self):
        self.events = deque()  # (timestamp, is_backspace)
        self.last_key_time = None
        self.pause_duration = 0.0

    def record(self, key_count=0, backspace_count=0, timestamp=None):
        now = float(timestamp or time.time())
        key_count = max(0, int(key_count or 0))
        backspace_count = max(0, int(backspace_count or 0))
        backspace_count = min(backspace_count, key_count)

        if self.last_key_time is not None:
            gap = max(0.0, now - self.last_key_time)
            if gap <= 120:
                self.pause_duration = round(gap, 2)
        if key_count:
            self.last_key_time = now
            for _ in range(key_count - backspace_count):
                self.events.append((now, False))
            for _ in range(backspace_count):
                self.events.append((now, True))

        self._prune(now)
        return self.snapshot(now)

    def _prune(self, now):
        cutoff = now - WINDOW_SECS
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()

    def snapshot(self, now=None):
        now = float(now or time.time())
        self._prune(now)
        total = len(self.events)
        backspaces = sum(1 for _, is_bs in self.events if is_bs)
        window = WINDOW_SECS
        kpm = (total / window) * 60.0
        bsr = (backspaces / total) if total else None
        live_pause = max(0.0, now - self.last_key_time) if self.last_key_time is not None else None
        return {
            'kpm': round(kpm, 1) if total else None,
            'backspace_ratio': round(bsr, 3) if bsr is not None else None,
            'pause_duration': round(live_pause, 2) if live_pause is not None else None,
            'keypress_count': total,
            'backspace_count': backspaces,
            'available': self.last_key_time is not None and (now - self.last_key_time) <= 120.0,
        }

    def reset(self):
        self.events.clear()
        self.last_key_time = None
        self.pause_duration = 0.0


_typing = {}


def get_typing_metrics(user_id):
    user_id = int(user_id)
    if user_id not in _typing:
        _typing[user_id] = TypingMetrics()
    return _typing[user_id]


def reset_typing_metrics(user_id):
    _typing[int(user_id)] = TypingMetrics()
