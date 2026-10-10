"""OPTIONAL camera. Disabled by default (ENABLE_CAMERA=false). Never imported at startup, never retried in a loop, never blocks:
init runs once in a daemon thread with a hard timeout. Failure = one log line and Aurora continues. Hook point for later NOVA vision work."""
import logging, threading
log = logging.getLogger("aurora.camera")

class CameraService:
    def __init__(self, enabled): self.enabled, self.ok, self.reason, self._cam = enabled, False, "disabled", None
    def start(self, timeout=5.0):
        if not self.enabled: return False
        def init():
            try:
                from picamera2 import Picamera2
                self._cam = Picamera2(); self._cam.start(); self.ok, self.reason = True, "ok"
            except Exception as e: self.reason = f"{type(e).__name__}: {e}"
        t = threading.Thread(target=init, daemon=True, name="camera-init"); t.start(); t.join(timeout)
        if not self.ok: log.warning("camera unavailable (%s) - continuing without it", self.reason if not t.is_alive() else "init timed out")
        return self.ok
    def capture(self):
        return self._cam.capture_array() if self.ok else None
    def stop(self):
        try:
            if self._cam: self._cam.stop(); self._cam.close()
        except Exception: log.exception("camera stop failed")
