"""Bluetooth speaker output. OUTPUT ONLY: never opens or configures the microphone/ALSA capture device.
Playback = a raw-PCM subprocess (paplay for PulseAudio/PipeWire, or aplay for ALSA/BlueALSA) fed in real time, so playback timing is known
and the mouth can follow it. Backend is chosen from what is actually installed; it never silently falls back to the wired amplifier."""
import logging, math, struct, subprocess, time, wave
from dataclasses import dataclass
log = logging.getLogger("aurora.out")

def _run(cmd, timeout=4):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception: return ""

@dataclass
class Target:
    kind: str; device: str; label: str

def _mac_us(mac): return mac.replace(":", "_").upper()

def resolve_output(s, run=_run):
    """Pure decision logic (tested): returns Target or None."""
    mac = s.bt_mac
    if s.audio_backend == "aplay":
        dev = s.alsa_playback_device or (f"bluealsa:DEV={mac},PROFILE=a2dp" if mac else "")
        return Target("aplay", dev, f"ALSA {dev}") if dev else None
    sinks = [l.split("\t") for l in run(["pactl", "list", "short", "sinks"]).splitlines() if "\t" in l]
    names = [c[1] for c in sinks if len(c) > 1]
    if s.audio_sink and s.audio_sink in names: return Target("paplay", s.audio_sink, f"sink {s.audio_sink}")
    bt = [n for n in names if "bluez" in n.lower()]
    if mac: bt = [n for n in bt if _mac_us(mac) in n.upper()]
    if bt and s.audio_backend in ("auto", "paplay"): return Target("paplay", bt[0], f"bluetooth sink {bt[0]}")
    if s.audio_backend == "auto" and mac and "bluealsa" in run(["aplay", "-L"]).lower(): return Target("aplay", f"bluealsa:DEV={mac},PROFILE=a2dp", "BlueALSA")
    return None

def build_command(t: Target, rate):
    if t.kind == "paplay": return ["paplay", "--raw", f"--rate={rate}", "--channels=1", "--format=s16le"] + ([f"--device={t.device}"] if t.device else [])
    return ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", str(rate), "-D", t.device]

def silence(ms, rate): return b"\x00\x00" * int(rate * ms / 1000)

class BluetoothOutput:
    def __init__(self, s, run=_run, popen=subprocess.Popen, clock=time.monotonic, sleep=time.sleep):
        self.s, self.run, self.popen, self.clock, self.sleep, self._t, self._last_try, self.last_error = s, run, popen, clock, sleep, None, -1e9, ""
    def latency_s(self): return self.s.output_latency_ms / 1000.0
    def target(self):
        if self._t is None and self.clock() - self._last_try > 5:                     # rate-limited re-discovery (speaker may connect later)
            self._last_try = self.clock(); self._t = resolve_output(self.s, self.run)
            if self._t is None and self.s.bt_mac and self.s.audio_backend != "aplay":
                self.run(["bluetoothctl", "connect", self.s.bt_mac], timeout=12); self._t = resolve_output(self.s, self.run)
            log.info("output target: %s", self._t.label if self._t else "NONE (no Bluetooth sink found)")
        return self._t
    def health(self):
        t = self.target(); return (True, t.label) if t else (False, self.last_error or "no Bluetooth speaker/sink found (is it connected? see tools/check_bt_audio.py)")
    def play(self, pcm: bytes, rate: int, on_chunk=None, cancel=None, chunk_ms=40, lead_s=0.25):
        """Blocks until the audio has been delivered. Returns (ok, t0, n_chunks, chunk_s). on_chunk(i, t0) is called just before chunk i is written."""
        t = self.target()
        if not t: self.last_error = "no Bluetooth output"; return False, None, 0, chunk_ms / 1000
        step = int(rate * chunk_ms / 1000) * 2; n = math.ceil(len(pcm) / step); cs = chunk_ms / 1000
        try: p = self.popen(build_command(t, rate), stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.last_error = f"cannot start {t.kind}: {e}"; self._t = None; log.error(self.last_error); return False, None, 0, cs
        ok, t0 = True, self.clock()
        try:
            for i in range(n):
                if cancel is not None and cancel.is_set(): p.terminate(); ok = False; break
                wait = (t0 + i * cs - lead_s) - self.clock()
                if wait > 0: self.sleep(wait)
                if on_chunk: on_chunk(i, t0)
                p.stdin.write(pcm[i * step:(i + 1) * step]); p.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            ok = False; self.last_error = f"playback pipe broke (speaker disconnected?): {e}"; self._t = None; log.error(self.last_error)
        finally:
            try: p.stdin.close()
            except Exception: pass
            try: p.wait(timeout=n * cs + 8)
            except Exception: p.kill()
        return ok, t0, n, cs

def make_hum_pcm(rate=24000):
    notes, dur, out = [220, 247, 262, 247, 220, 196, 220], 1.8, bytearray()
    for i in range(int(rate * dur)):
        t = i / rate; f = notes[min(len(notes) - 1, int(t / (dur / len(notes))))]; env = min(1.0, t / .15, (dur - t) / .2)
        out += struct.pack("<h", int(.10 * env * (math.sin(2 * math.pi * f * t) + .25 * math.sin(4 * math.pi * f * t)) * 32767))
    return bytes(out)
