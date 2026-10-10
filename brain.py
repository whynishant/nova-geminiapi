"""AURORA x NOVA - orchestration only (lifecycle + interaction state). Pygame stays on the main thread (as in the original Aurora).
Subsystems, each independent and failure-isolated:
  mic.py (INMP441/arecord)  wake.py (Vosk)  ai_service.py (Gemini)  audio_out.py (Bluetooth)  speech.py (TTS+mouth)
  touch.py (TTP223)  expression.py (arbitration)  camera_service.py (optional)  face.py/animation.py/emotion.py (original visuals)
Run:  cd ~/robot_brain && python3 brain.py        Stop: Ctrl+C, ESC on the face window, or ./stop.sh
"""
import logging, random, signal, sys, threading, time
import settings
settings.load_env()
from emotion import Emotion
from face import FaceEngine
from state import State, StateMachine
from expression import ExpressionManager
log = logging.getLogger("aurora")

class Aurora:
    def __init__(self, s=None, face=None, mic=None, wake=None, ai=None, output=None, speech=None, camera=None, touch_factory=None):
        self.s = s or settings.Settings()
        self.stop_evt, self.talk_request = threading.Event(), threading.Event()
        self.face = face or FaceEngine(); self.state = StateMachine(); self.expr = ExpressionManager(self.face)
        self.subsystems = {}                                   # name -> (ok, detail) for the startup report
        self.mic, self.wake, self.ai, self.output, self.speech, self.camera, self.touch = mic, wake, ai, output, speech, camera, None
        self._init(self.s, touch_factory)
        self.state.subscribe(self._on_state)
    # ---------- construction: every subsystem in its own try/except; none can stop the others ----------
    def _try(self, name, fn):
        try: r = fn(); self.subsystems[name] = (True, "ok"); return r
        except Exception as e:
            log.error("%s unavailable: %s", name, e); self.subsystems[name] = (False, f"{type(e).__name__}: {e}"); return None
    def _init(self, s, touch_factory):
        from mic import MicCapture
        from wake import WakeWordDetector
        from ai_service import GeminiService
        from audio_out import BluetoothOutput
        from speech import SpeechService
        from camera_service import CameraService
        if self.mic is None: self.mic = self._try("microphone", lambda: MicCapture(s.capture_device, s.sample_rate))
        if self.wake is None and s.wake_enabled: self.wake = self._try("wake_word", lambda: WakeWordDetector(s.vosk_model_path, s.wake_words, s.sample_rate))
        if self.wake is not None and not getattr(self.wake, "available", False):
            self.subsystems["wake_word"] = (False, getattr(self.wake, "reason", "unavailable")); self.wake = None
        if self.mic is not None and self.subsystems.get("microphone", (0,))[0]: self.subsystems["microphone"] = (True, f"configured {s.capture_device} (opened on first listen)")
        def mk_ai():
            if not s.gemini_api_key: raise ValueError("GEMINI_API_KEY missing (see .env.example)")
            return GeminiService(s)
        if self.ai is None: self.ai = self._try("gemini", mk_ai)
        if self.output is None: self.output = self._try("bluetooth_output", lambda: BluetoothOutput(s))
        if self.speech is None and self.ai and self.output: self.speech = SpeechService(s, self.ai.synthesize, self.output, self.face, self.expr)
        if self.camera is None: self.camera = self._try("camera", lambda: CameraService(s.enable_camera))
        self.touch_to_talk = (s.touch_to_talk == "true") or (s.touch_to_talk == "auto" and self.wake is None)
        self._touch_factory = touch_factory
    # ---------- state -> expression ----------
    def _on_state(self, old, new):
        self.expr.set_baseline({State.IDLE: Emotion.IDLE, State.LISTENING: Emotion.LISTENING, State.THINKING: Emotion.THINKING, State.SPEAKING: Emotion.THINKING}[new])   # SPEAKING shows TALKING only once audio really starts (speech.py)
    # ---------- touch: expression only (+ optional touch-to-talk fallback); never blocks ----------
    def on_touch(self, ev):
        s = self.s
        if ev == "START": self.expr.overlay("touch_first", s.touch_first); 
        elif ev == "REPEAT": self.expr.overlay("touch_repeat", s.touch_repeat)
        elif ev == "HOLD": self.expr.overlay("touch_hold", s.touch_hold)
        elif ev == "RELEASE":
            for n in ("touch_first", "touch_repeat", "touch_hold"): self.expr.release(n, 1.0 if n != "touch_first" else 0.8)
        if ev == "START" and self.touch_to_talk and self.state.state == State.IDLE: self.talk_request.set()
    def _start_touch(self):
        from touch import GestureDetector, TouchInput
        g = GestureDetector(self.on_touch, self.s.touch_hold_s, self.s.touch_repeat_count, self.s.touch_repeat_window_s, self.s.touch_debounce_s)
        self.touch = (self._touch_factory or (lambda gd: TouchInput(self.s.touch_pin, self.s.touch_debounce_s, gd)))(g)
        ok = self.touch.start(); self.subsystems["touch"] = (bool(ok), "ok" if ok else "unavailable"); 
    # ---------- microphone helpers ----------
    def _mic_on(self):
        if self.mic and not self.mic.active and not self.stop_evt.is_set(): self.mic.start()
    def _mic_off(self):
        if self.mic: self.mic.stop()
    def _abort(self): return self.stop_evt.is_set()
    # ---------- the conversation worker ----------
    def conversation_loop(self):
        from mic import MicError
        backoff, next_hum = 1.0, time.monotonic() + random.uniform(self.s.hum_min, self.s.hum_max)
        while not self.stop_evt.is_set():
            try:
                self.state.set(State.IDLE); reason = self._await_activation(lambda: next_hum)
                if reason == "hum": self._hum(); next_hum = time.monotonic() + random.uniform(self.s.hum_min, self.s.hum_max); continue
                if reason in ("wake", "touch"): self._session(reason); next_hum = time.monotonic() + random.uniform(self.s.hum_min, self.s.hum_max)
                backoff = 1.0
            except MicError as e:
                log.error("microphone problem: %s (retry in %.0fs)", e, backoff); self._mic_off(); self.expr.overlay("error", Emotion.ERROR, 1.2)
                self.stop_evt.wait(backoff); backoff = min(backoff * 2, 10)
            except Exception:
                log.exception("conversation loop error"); self.expr.overlay("error", Emotion.ERROR, 1.2); self.stop_evt.wait(1)
        self._mic_off(); self.state.set(State.IDLE)
    def _await_activation(self, hum_at):
        if self.wake is not None and self.mic is not None:
            self._mic_on()
            while not self.stop_evt.is_set():
                if self.wake.listen(self.mic, lambda: self.stop_evt.is_set() or self.talk_request.is_set() or (self.s.humming and time.monotonic() >= hum_at())):
                    return "wake"
                if self.talk_request.is_set(): self.talk_request.clear(); return "touch"
                if self.s.humming and time.monotonic() >= hum_at(): return "hum"
            return None
        while not self.stop_evt.is_set():                       # no wake word: touch-to-talk fallback only (never an open microphone)
            if self.talk_request.wait(0.2): self.talk_request.clear(); return "touch"
            if self.s.humming and time.monotonic() >= hum_at(): return "hum"
        return None
    def _hum(self):
        if not self.speech: return
        self._mic_off()
        from audio_out import make_hum_pcm
        try: self.speech.play_effect(make_hum_pcm(self.s.tts_rate), self.s.tts_rate)
        except Exception: log.exception("humming failed")
        finally: self.expr.set_baseline(Emotion.IDLE)
    def _session(self, reason):
        if not (self.mic and self.ai): log.warning("cannot start a conversation: mic=%s ai=%s", bool(self.mic), bool(self.ai)); self.expr.overlay("error", Emotion.ERROR, 1.2); return
        from mic import record_utterance
        self._mic_on(); self.expr.overlay("wake", Emotion.WAKING, 0.5) if reason == "wake" else None
        first = True
        while not self.stop_evt.is_set():
            self.state.set(State.LISTENING)
            wav = record_utterance(self.mic, start_timeout=None if first else (self.s.followup_s or 0.01), should_abort=self._abort)
            if wav is None:
                if first: self.expr.overlay("curious", Emotion.CURIOUS, 0.6)
                break
            first = False; self.state.set(State.THINKING)
            reply = self.ai.converse(wav)                       # network on this worker thread; animation keeps running
            log.info("user: %s | aura: %s", reply.transcript, reply.text)
            if not reply.text:
                self.expr.overlay("curious", Emotion.CURIOUS, 0.6); break
            self._mic_off()                                     # voluntary: stops Aurora from hearing its own voice (not caused by Bluetooth)
            self.state.set(State.SPEAKING)
            played = self.speech.speak(reply.text, reply.emotion or None) if self.speech else False
            if not played: log.warning("reply could not be spoken (TTS/Bluetooth) - see log"); self.expr.overlay("error", Emotion.ERROR, 1.0)
            if not reply.ok or self.s.followup_s <= 0: break
            self._mic_on()
        self.state.set(State.IDLE); self.expr.overlay("after", Emotion.SHY, 0.45)     # original Aurora: tiny shy after an interaction
        if not self.wake: self._mic_off()
    # ---------- lifecycle ----------
    def report(self):
        lines = ["==== AURORA READY ===="] + [f"  [{'OK ' if ok else 'OFF'}] {n}: {d}" for n, (ok, d) in sorted(self.subsystems.items())]
        lines.append(f"  mode: {'wake word' if self.wake else 'NO wake word'}; touch-to-talk fallback: {self.touch_to_talk}")
        return "\n".join(lines)
    def start_background(self):
        self.expr.start(); self.face.start()
        if self.camera and getattr(self.camera, "enabled", True):
            ok = bool(self._try("camera", lambda: self.camera.start())); self.subsystems["camera"] = (ok, "ok" if ok else f"optional, not running ({self.camera.reason})")
        else: self.subsystems["camera"] = (False, "disabled (ENABLE_CAMERA=false) - optional")
        if self.output is not None and hasattr(self.output, "health"):
            def probe():                                        # may call pactl/bluetoothctl: keep it off the main thread
                ok, detail = self.output.health(); self.subsystems["bluetooth_output"] = (ok, detail); log.info("bluetooth output: %s", detail)
            threading.Thread(target=probe, daemon=True, name="bt-probe").start()
        self._start_touch()
        self.worker = threading.Thread(target=self.conversation_loop, daemon=True, name="conversation"); self.worker.start()
    def shutdown(self):
        if self.stop_evt.is_set(): return
        log.info("shutting down"); self.stop_evt.set(); self.talk_request.set()
        for fn in (lambda: self.speech and self.speech.cancel(), self._mic_off, lambda: self.touch and self.touch.stop(), lambda: self.camera and self.camera.stop(), self.expr.stop, self.face.stop):
            try: fn()
            except Exception: log.exception("shutdown step failed")
    def run(self):
        for p in self.s.validate(): log.error("config: %s", p)
        self.start_background(); print(self.report(), flush=True)
        signal.signal(signal.SIGTERM, lambda *a: self.shutdown()); signal.signal(signal.SIGINT, lambda *a: self.shutdown())
        try: self.face.run()                                     # main thread (pygame requirement) until ESC / signal
        finally: self.shutdown()

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Aurora().run()

if __name__ == "__main__": main()
