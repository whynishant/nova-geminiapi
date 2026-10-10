"""Expression arbitration. The face has ONE emotion; several parts of Aurora want to set it (conversation state, touch).
baseline = what the interaction state wants; overlays (touch) win while active and then release back to the baseline.
Uses ONLY the existing Emotion set and face.set_emotion - no new visuals."""
import logging, threading, time
from emotion import Emotion
log = logging.getLogger("aurora.expr")
PRIORITY = {"touch_first": 1, "touch_repeat": 2, "touch_hold": 3}

def to_emotion(v, default=Emotion.IDLE):
    if isinstance(v, Emotion): return v
    try: return Emotion(str(v).lower())
    except ValueError: return default

class ExpressionManager:
    def __init__(self, face, clock=time.monotonic):
        self.face, self.clock, self._lock = face, clock, threading.Lock()
        self._baseline, self._overlays, self._applied = Emotion.IDLE, {}, None   # overlays: name -> (emotion, expires_at|None)
        self._stop = threading.Event(); self._t = None
    def start(self):
        self._apply(); self._t = threading.Thread(target=self._run, daemon=True, name="expression"); self._t.start()
    def stop(self): self._stop.set()
    def _run(self):
        while not self._stop.wait(0.03): self._apply()
    def set_baseline(self, emotion):
        with self._lock: self._baseline = to_emotion(emotion)
        self._apply()
    def overlay(self, name, emotion, duration=None):
        with self._lock: self._overlays[name] = (to_emotion(emotion), None if duration is None else self.clock() + duration)
        self._apply()
    def release(self, name, hold_s=0.0):
        """Remove an overlay now, or after hold_s (so the reaction stays visible a moment after the finger leaves)."""
        with self._lock:
            if name in self._overlays: self._overlays[name] = (self._overlays[name][0], self.clock() + hold_s)
        self._apply()
    def effective(self):
        now = self.clock()
        with self._lock:
            for n in [n for n, (_, exp) in self._overlays.items() if exp is not None and exp <= now]: del self._overlays[n]
            if self._overlays:
                n = max(self._overlays, key=lambda k: PRIORITY.get(k, 0)); return self._overlays[n][0]
            return self._baseline
    def _apply(self):
        e = self.effective()
        if e != self._applied:
            self._applied = e
            try: self.face.set_emotion(e)
            except Exception: log.exception("face.set_emotion failed")
