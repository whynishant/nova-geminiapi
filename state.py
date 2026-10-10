"""One interaction state, so listening / thinking / speaking can never contradict each other."""
import enum, logging, threading
log = logging.getLogger("aurora.state")

class State(str, enum.Enum):
    IDLE = "idle"; LISTENING = "listening"; THINKING = "thinking"; SPEAKING = "speaking"

class StateMachine:
    def __init__(self): self._s, self._lock, self._subs = State.IDLE, threading.Lock(), []
    @property
    def state(self): return self._s
    def subscribe(self, fn): self._subs.append(fn)
    def set(self, new):
        with self._lock: old, self._s = self._s, new
        if old != new:
            log.info("state %s -> %s", old.value, new.value)
            for fn in list(self._subs):
                try: fn(old, new)
                except Exception: log.exception("state subscriber failed")
