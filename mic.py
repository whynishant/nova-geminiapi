"""INMP441 capture. ONE owner of the ALSA capture device (arecord), used first by the wake-word detector and then by the VAD recorder
(same thread, same stream), so nothing competes for the mic. Nothing in this file knows about Bluetooth or any output device.
The VAD algorithm and constants are the ones from the working Aurora build (config.VAD_*)."""
import io, logging, math, os, select, subprocess, time, wave
from array import array
import config
log = logging.getLogger("aurora.mic")

class MicError(RuntimeError): pass

def rms_of(data):
    s = array("h", data[: len(data) // 2 * 2])
    return math.sqrt(sum(x * x for x in s) / max(1, len(s)))

class MicCapture:
    def __init__(self, device, rate=16000, popen=subprocess.Popen, chunk_ms=100, read_timeout=3.0):
        self.device, self.rate, self.popen, self.chunk, self.read_timeout = device, rate, popen, int(rate * 2 * chunk_ms / 1000), read_timeout
        self.proc = None
    @property
    def active(self): return self.proc is not None and self.proc.poll() is None
    def start(self):
        if self.active: return
        cmd = ["arecord", "-q", "-D", self.device, "-f", "S16_LE", "-c", "1", "-r", str(self.rate), "-t", "raw", "-"]
        try: self.proc = self.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        except Exception as e: self.proc = None; raise MicError(f"cannot start arecord on {self.device}: {e}")
    def stop(self):
        p, self.proc = self.proc, None
        if not p: return
        try:
            p.terminate()
            try: p.wait(timeout=2)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        except Exception: log.exception("mic stop failed")
        try: p.stdout.close()
        except Exception: pass
    def read(self, nbytes=None):
        if not self.active: raise MicError("microphone not running")
        n, buf = nbytes or self.chunk, b""
        while len(buf) < n:
            r, _, _ = select.select([self.proc.stdout], [], [], self.read_timeout)
            if not r: raise MicError("microphone produced no audio (device busy or wrong ALSA_CAPTURE_DEVICE?)")
            d = os.read(self.proc.stdout.fileno(), n - len(buf))
            if not d: raise MicError("microphone stream ended")
            buf += d
        return buf

def record_utterance(mic: MicCapture, start_timeout=None, should_abort=None, clock=time.monotonic):
    """Adaptive VAD recording on the already-running mic stream (original Aurora algorithm). Returns WAV bytes, or None if nobody spoke."""
    cms = mic.chunk / (mic.rate * 2)
    start_timeout = config.VAD_START_TIMEOUT_SECONDS if start_timeout is None else start_timeout
    levels = [rms_of(mic.read()) for _ in range(max(1, int(config.VAD_CALIBRATION_SECONDS / cms)))]
    floor = max(sum(levels) / len(levels), config.VAD_MIN_RMS); thr = max(config.VAD_MIN_RMS, floor * config.VAD_SPEECH_MULTIPLIER)
    log.info("noise floor %.0f speech threshold %.0f", floor, thr)
    pre_n = max(1, int(config.VAD_PRE_ROLL_SECONDS / cms)); pre, chunks = [], []
    started, t_start, silence_since, t_wait = False, None, None, clock()
    while True:
        if should_abort and should_abort(): return None
        data = mic.read(); rms = rms_of(data); now = clock()
        if not started:
            pre = (pre + [data])[-pre_n:]
            if rms >= thr: started, t_start = True, now; chunks.extend(pre); log.info("speech detected")
            elif now - t_wait >= start_timeout: return None
        else:
            chunks.append(data)
            if rms >= thr: silence_since = None
            else:
                silence_since = silence_since or now
                if now - silence_since >= config.VAD_END_SILENCE_SECONDS and now - t_start >= config.VAD_MIN_SPEECH_SECONDS: break
            if now - t_start >= config.VAD_MAX_RECORD_SECONDS: break
    b = io.BytesIO()
    with wave.open(b, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(mic.rate); w.writeframes(b"".join(chunks))
    return b.getvalue()
