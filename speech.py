"""Speech lifecycle: text -> Gemini TTS -> Bluetooth playback, with the mouth driven by the loudness of the audio actually being played.
Mouth events are scheduled from the moment playback begins (+ OUTPUT_LATENCY_MS), not from a free-running timer.
A newer speak() cancels an older one (generation counter); the mouth is always restored to rest afterwards."""
import heapq, itertools, logging, math, threading, time
from array import array
from audio_out import silence
from emotion import Emotion
from expression import to_emotion
log = logging.getLogger("aurora.speech")

def chunk_levels(pcm, rate, chunk_ms=40):
    """Per-chunk loudness 0..1, normalised to this utterance (so quiet and loud voices both open the mouth fully)."""
    n = int(rate * chunk_ms / 1000) * 2; rms = []
    for i in range(0, len(pcm), n):
        a = array("h", pcm[i:i + n][: len(pcm[i:i + n]) // 2 * 2]); rms.append(math.sqrt(sum(x * x for x in a) / max(1, len(a))))
    voiced = sorted(r for r in rms if r > 1)
    ref = (voiced[int(len(voiced) * .9) - 1] if len(voiced) > 1 else (voiced[0] if voiced else 1)) or 1
    return [min(1.0, (r / ref)) ** .8 if r > 1 else 0.0 for r in rms]

class MouthTimeline:
    """One thread applies face.set_mouth_audio(level) at the right moments. Stale generations are dropped."""
    def __init__(self, face, clock=time.monotonic):
        self.face, self.clock, self._h, self._c, self._gen, self._seq = face, clock, [], threading.Condition(), 0, itertools.count()
        threading.Thread(target=self._run, daemon=True, name="mouth").start()
    def new_generation(self):
        with self._c: self._gen += 1; self._h.clear(); g = self._gen
        return g
    def schedule(self, due, gen, value):
        with self._c: heapq.heappush(self._h, (due, next(self._seq), gen, value)); self._c.notify()
    def _run(self):
        while True:
            with self._c:
                while not self._h or self._h[0][0] > self.clock(): self._c.wait(timeout=None if not self._h else max(0.0, self._h[0][0] - self.clock()))
                _, _, gen, val = heapq.heappop(self._h); cur = self._gen
            if gen == cur:
                try: self.face.set_mouth_audio(val)
                except Exception: log.exception("mouth update failed")

class SpeechService:
    def __init__(self, s, tts, output, face, expression, clock=time.monotonic):
        self.s, self.tts, self.output, self.face, self.expr, self.clock = s, tts, output, face, expression, clock
        self.timeline = MouthTimeline(face, clock); self._lock, self._seq_lock, self._seq, self._cancel = threading.Lock(), threading.Lock(), 0, threading.Event()
    def cancel(self): self._cancel.set()
    def speak(self, text, emotion=None):
        """Blocks until the speaker has finished and the mouth is back at rest. Returns True if audio was actually played."""
        with self._seq_lock: self._seq += 1; my = self._seq; self._cancel.set()
        with self._lock:
            if my != self._seq: return False                      # a newer request superseded this one
            self._cancel.clear()
            try: pcm = self.tts(text)                              # network call - on the worker thread, never the animation thread
            except Exception: log.exception("tts crashed"); pcm = None
            if not pcm: log.warning("no speech audio produced"); return False
            rate = self.s.tts_rate; pcm = silence(self.s.lead_silence_ms, rate) + pcm      # BT sinks often clip the first ~0.3 s
            levels = chunk_levels(pcm, rate); gen = self.timeline.new_generation(); lat = self.output.latency_s(); state = {"first": True}
            def on_chunk(i, t0):
                if state["first"]:
                    state["first"] = False
                    self.face.set_mouth_audio(0.0)                 # hand the mouth to the audio signal as soon as playback starts
                    self.expr.set_baseline(to_emotion(emotion, Emotion.TALKING)); self.face.set_talking_level(0.6)
                    for k, lv in enumerate(levels): self.timeline.schedule(t0 + k * .04 + lat, gen, lv)
            ok, t0, n, cs = self.output.play(pcm, rate, on_chunk=on_chunk, cancel=self._cancel)
            if t0 is None: return False
            end_due = t0 + n * cs + lat
            self.timeline.schedule(end_due, gen, None)             # mouth back to rest exactly when the sound ends
            while not self._cancel.is_set() and self.clock() < end_due: self._cancel.wait(min(.05, end_due - self.clock()))
            self.timeline.new_generation(); self.face.set_mouth_audio(None); self.face.set_talking_level(0)
            return ok
    def play_effect(self, pcm, rate, emotion=Emotion.HUMMING):
        """Non-speech sound (idle humming): original HUMMING expression, mouth stays on the original animation."""
        with self._lock:
            self._cancel.clear(); self.expr.set_baseline(emotion); self.face.set_talking_level(.25)
            try: self.output.play(silence(self.s.lead_silence_ms, rate) + pcm, rate, cancel=self._cancel)
            finally: self.face.set_talking_level(0)
