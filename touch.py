"""Touch input (TTP223): hardware adapter + gesture logic. Callbacks are tiny and non-blocking (no network, no audio, no sleeping).
Events: START (once per touch), HOLD (once, after hold_s - a held finger never re-fires), REPEAT (n touches inside the window), RELEASE."""
import logging, threading, time
log = logging.getLogger("aurora.touch")
START, HOLD, REPEAT, RELEASE = "START", "HOLD", "REPEAT", "RELEASE"

class GestureDetector:
    def __init__(self, emit, hold_s=2.5, repeat_count=3, repeat_window_s=10.0, min_gap_s=0.08, clock=time.monotonic, timer=threading.Timer):
        self.emit, self.hold_s, self.n, self.win, self.min_gap, self.clock, self.Timer = emit, hold_s, repeat_count, repeat_window_s, min_gap_s, clock, timer
        self._down, self._times, self._tok, self._timer, self._last_release, self._lock = False, [], 0, None, -1e9, threading.Lock()
    def pressed(self):
        with self._lock:
            now = self.clock()
            if self._down or now - self._last_release < self.min_gap: return        # bounce / duplicate while held
            self._down = True; self._tok += 1; tok = self._tok
            self._times = [t for t in self._times if now - t < self.win] + [now]
            count = len(self._times)
            self._timer = self.Timer(self.hold_s, lambda: self._hold(tok)); self._timer.daemon = True; self._timer.start()
        self.emit(START)
        if count >= self.n: self.emit(REPEAT)
    def _hold(self, tok):
        with self._lock:
            if not self._down or tok != self._tok: return
        self.emit(HOLD)
    def released(self):
        with self._lock:
            if not self._down: return
            self._down = False; self._tok += 1; self._last_release = self.clock()
            if self._timer: self._timer.cancel()
        self.emit(RELEASE)

class TouchInput:
    """gpiozero adapter. Failure to initialise is reported and returns False: the rest of Aurora keeps running."""
    def __init__(self, pin, debounce_s, gestures: GestureDetector): self.pin, self.debounce, self.g, self.dev = pin, debounce_s, gestures, None
    def start(self):
        try:
            from gpiozero import Button
            self.dev = Button(self.pin, pull_up=False, bounce_time=self.debounce)
            self.dev.when_pressed, self.dev.when_released = self.g.pressed, self.g.released
            log.info("touch sensor ready on GPIO%d", self.pin); return True
        except Exception as e:
            log.warning("touch sensor unavailable (GPIO%s): %s", self.pin, e); return False
    def stop(self):
        try:
            if self.dev: self.dev.close()
        except Exception: log.exception("touch close failed")
