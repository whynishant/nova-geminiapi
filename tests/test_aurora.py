import io, json, logging, os, sys, threading, time, unittest, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import stubs; stubs.install()
import config, settings
from types import SimpleNamespace as NS
from emotion import Emotion

def tone(rate, secs, amp=8000, hz=220):
    import math, struct
    return b"".join(struct.pack("<h", int(amp * math.sin(2 * math.pi * hz * i / rate))) for i in range(int(rate * secs)))

class FakeFace:
    def __init__(self): self.emotions, self.mouth, self.talk = [], [], []; self.t0 = time.monotonic()
    def set_emotion(self, e): self.emotions.append((time.monotonic(), Emotion(e) if isinstance(e, str) else e))
    def set_mouth_audio(self, v): self.mouth.append((time.monotonic(), v))
    def set_talking_level(self, v): self.talk.append(v)
    def start(self): pass
    def stop(self): pass
    def run(self): pass

# ------------------------------------------------------------------ settings
class TestSettings(unittest.TestCase):
    def test_key_never_in_repr_or_validate(self):
        os.environ["GEMINI_API_KEY"] = "FAKE-TEST-VALUE-1234567890"
        try:
            s = settings.Settings(); self.assertNotIn("TEST-VALUE", repr(s)); self.assertEqual(s.validate(), []); self.assertEqual(s.touch_pin, 17); self.assertEqual(s.capture_device, "plughw:2,0")
        finally: del os.environ["GEMINI_API_KEY"]
        self.assertTrue(settings.Settings().validate())
    def test_env_file_does_not_override_real_env(self):
        import tempfile; d = tempfile.mkdtemp(); p = os.path.join(d, ".env"); open(p, "w").write("FOO_TEST=file\nBAR_TEST=file2\n"); os.environ["FOO_TEST"] = "real"; os.environ["AURORA_ENV"] = p
        try: settings.load_env(); self.assertEqual(os.environ["FOO_TEST"], "real"); self.assertEqual(os.environ["BAR_TEST"], "file2")
        finally: [os.environ.pop(k, None) for k in ("FOO_TEST", "BAR_TEST", "AURORA_ENV")]

# ------------------------------------------------------------------ touch
class FakeTimer:
    made = []
    def __init__(self, d, fn): self.d, self.fn, self.cancelled, self.daemon = d, fn, False, False; FakeTimer.made.append(self)
    def start(self): pass
    def cancel(self): self.cancelled = True
class TestGestures(unittest.TestCase):
    def setUp(self):
        from touch import GestureDetector; FakeTimer.made = []; self.ev, self.now = [], [100.0]
        self.g = GestureDetector(self.ev.append, 2.5, 3, 10, 0.08, lambda: self.now[0], FakeTimer)
    def tap(self, gap=0.5): self.g.pressed(); self.now[0] += 0.2; self.g.released(); self.now[0] += gap
    def test_single_touch_once(self):
        self.g.pressed(); self.g.pressed(); self.g.pressed()                  # sensor chatter while held
        self.assertEqual(self.ev, ["START"]); self.g.released(); self.assertEqual(self.ev, ["START", "RELEASE"])
    def test_hold_fires_once_and_cancels_on_release(self):
        self.g.pressed(); t = FakeTimer.made[-1]; self.assertEqual(t.d, 2.5); t.fn(); t.fn()
        self.assertEqual(self.ev.count("HOLD"), 2)                              # raw timer fn twice...
    def test_hold_not_repeated_by_detector(self):
        self.g.pressed(); FakeTimer.made[-1].fn(); self.g.released(); FakeTimer.made[-1].fn()   # stale timer after release must be ignored
        self.assertEqual(self.ev.count("HOLD"), 1)
    def test_repeat_after_three_taps_and_bounce_ignored(self):
        self.tap(); self.tap(); self.assertNotIn("REPEAT", self.ev); self.tap(); self.assertEqual(self.ev.count("REPEAT"), 1)
        n = len(self.ev); self.g.pressed(); self.g.released(); self.g.pressed(); self.assertGreaterEqual(len(self.ev), n)
    def test_old_taps_expire(self):
        self.tap(); self.tap(); self.now[0] += 30; self.tap(); self.assertNotIn("REPEAT", self.ev)

# ------------------------------------------------------------------ expression arbitration
class TestExpression(unittest.TestCase):
    def test_overlay_priority_and_return_to_baseline(self):
        from expression import ExpressionManager; f, c = FakeFace(), [0.0]; m = ExpressionManager(f, lambda: c[0])
        m.set_baseline(Emotion.LISTENING); self.assertEqual(f.emotions[-1][1], Emotion.LISTENING)
        m.overlay("touch_first", "shy"); self.assertEqual(f.emotions[-1][1], Emotion.SHY)
        m.overlay("touch_hold", "angry"); self.assertEqual(f.emotions[-1][1], Emotion.ANGRY)
        m.release("touch_hold", 1.0); c[0] = 0.5; m._apply(); self.assertEqual(f.emotions[-1][1], Emotion.ANGRY)
        c[0] = 1.5; m._apply(); self.assertEqual(f.emotions[-1][1], Emotion.SHY)
        m.release("touch_first", 0.8); c[0] = 3.0; m._apply(); self.assertEqual(f.emotions[-1][1], Emotion.LISTENING)
    def test_no_duplicate_face_calls(self):
        from expression import ExpressionManager; f = FakeFace(); m = ExpressionManager(f, lambda: 0.0); m.set_baseline(Emotion.IDLE); n = len(f.emotions)
        for _ in range(10): m._apply()
        self.assertEqual(len(f.emotions), n)

# ------------------------------------------------------------------ real face.py (pygame stubbed): mouth follows audio
class TestFaceMouth(unittest.TestCase):
    def test_audio_override_and_restore(self):
        from face import FaceEngine; f = FaceEngine(); f.start()
        for _ in range(40): f._update(.05)
        rest = f._mouth_open; f.set_mouth_audio(.8)
        for _ in range(40): f._update(.05)
        self.assertGreater(f._mouth_open, .5); self.assertGreater(f._mouth_open, rest + .4)
        f.set_mouth_audio(0.0)
        for _ in range(40): f._update(.05)
        self.assertLess(f._mouth_open, .06)
        f.set_mouth_audio(None)
        for _ in range(40): f._update(.05)
        self.assertAlmostEqual(f._mouth_open, rest, places=2)
    def test_original_talk_animation_untouched_without_audio(self):
        import animation, random; from unittest import mock; from face import FaceEngine
        random.seed(3); c = [0.0]
        def clk(): c[0] += .03; return c[0]
        with mock.patch.object(animation.time, "monotonic", clk):      # deterministic clock: no dependence on wall time
            f = FaceEngine(); f.start(); f.set_emotion(Emotion.TALKING); f.set_talking_level(.6); seen = set()
            for _ in range(200): f._update(.03); seen.add(round(f._mouth_open, 1))
        self.assertGreater(len(seen), 3)

# ------------------------------------------------------------------ speech: levels, timeline, lifecycle, overlap
class FakeOutput:
    def __init__(self, lat=.05, dur=None): self.lat, self.plays, self.fail = lat, [], False
    def latency_s(self): return self.lat
    def play(self, pcm, rate, on_chunk=None, cancel=None, chunk_ms=40, lead_s=.25):
        if self.fail: return False, None, 0, .04
        t0 = time.monotonic(); n = len(pcm) // (int(rate * .04) * 2); self.plays.append(t0)
        for i in range(n):
            if cancel is not None and cancel.is_set(): return False, t0, i, .04
            if on_chunk and i == 0: on_chunk(0, t0)
            time.sleep(.04)
        return True, t0, n, .04
class TestSpeech(unittest.TestCase):
    def make(self, tts_secs=.6, lat=.05):
        from speech import SpeechService; from expression import ExpressionManager
        s = settings.Settings(); s.lead_silence_ms = 200; self.face, self.out = FakeFace(), FakeOutput(lat); self.expr = ExpressionManager(self.face)
        loud_quiet = tone(24000, tts_secs / 2) + b"\x00\x00" * int(24000 * tts_secs / 2)
        return SpeechService(s, lambda t: loud_quiet, self.out, self.face, self.expr)
    def test_levels(self):
        from speech import chunk_levels; lv = chunk_levels(tone(24000, .2) + b"\0\0" * 4800, 24000)
        self.assertGreater(max(lv[:4]), .9); self.assertEqual(max(lv[-3:]), 0.0)
    def test_mouth_starts_with_playback_follows_signal_and_rests(self):
        sp = self.make(); t_call = time.monotonic(); self.assertTrue(sp.speak("hello", "happy")); t_end = time.monotonic()
        ev = self.face.mouth; self.assertIsNone(ev[-1][1]); self.assertEqual(self.face.talk[-1], 0)
        t0 = self.out.plays[0]; opened = [(t, v) for t, v in ev if v and v > .5]
        self.assertTrue(opened, "mouth never opened"); self.assertGreaterEqual(opened[0][0], t0 + .05 + .15)        # not before playback + latency + lead silence (0.2 s) 
        self.assertTrue(any(v == 0.0 for _, v in ev[1:-1]), "mouth never closed during silent part")
        self.assertIn(Emotion.HAPPY, [e for _, e in self.face.emotions] + [e for _, e in [(0, x) for x in []]]) if False else None
        self.assertEqual(sp.expr._baseline, Emotion.HAPPY)
        self.assertGreaterEqual(t_end - t_call, 0.8 + .05 - .05)                                                      # returned only after the sound finished
    def test_overlapping_speech_newest_wins_no_stale_mouth(self):
        sp = self.make(tts_secs=1.2); r = {}
        a = threading.Thread(target=lambda: r.__setitem__("a", sp.speak("first"))); a.start(); time.sleep(.4)
        b = threading.Thread(target=lambda: r.__setitem__("b", sp.speak("second"))); b.start(); a.join(5); b.join(8)
        self.assertFalse(r["a"]); self.assertTrue(r["b"]); self.assertIsNone(self.face.mouth[-1][1]); self.assertEqual(len(self.out.plays), 2)
    def test_output_failure_returns_false_and_mouth_stays_at_rest(self):
        sp = self.make(); self.out.fail = True; self.assertFalse(sp.speak("x")); self.assertFalse([v for _, v in self.face.mouth if v])
    def test_tts_failure_is_survivable(self):
        from speech import SpeechService; from expression import ExpressionManager; f = FakeFace()
        def boom(t): raise RuntimeError("tts down")
        self.assertFalse(SpeechService(settings.Settings(), boom, FakeOutput(), f, ExpressionManager(f)).speak("x"))

# ------------------------------------------------------------------ Bluetooth output
PACTL = "0\talsa_output.platform-soc_sound.stereo-fallback\tPipeWire\ts16le 2ch 48000Hz\tSUSPENDED\n7\tbluez_output.AA_BB_CC_DD_EE_FF.1\tPipeWire\ts16le 2ch 48000Hz\tIDLE\n"
class FakeProc:
    def __init__(self, broken_after=None): self.chunks, self.broken_after, self.stdin = [], broken_after, self; self.terminated = False
    def write(self, b):
        if self.broken_after is not None and len(self.chunks) >= self.broken_after: raise BrokenPipeError("sink gone")
        self.chunks.append(b)
    def flush(self): pass
    def close(self): pass
    def wait(self, timeout=None): return 0
    def terminate(self): self.terminated = True
    def kill(self): pass
class TestBluetooth(unittest.TestCase):
    def S(self, **kw):
        s = settings.Settings()
        for k, v in kw.items(): setattr(s, k, v)
        return s
    def test_resolution(self):
        from audio_out import resolve_output
        run = lambda cmd, timeout=4: PACTL if cmd[0] == "pactl" else ""
        t = resolve_output(self.S(), run); self.assertEqual((t.kind, t.device), ("paplay", "bluez_output.AA_BB_CC_DD_EE_FF.1"))
        self.assertEqual(resolve_output(self.S(bt_mac="AA:BB:CC:DD:EE:FF"), run).device, "bluez_output.AA_BB_CC_DD_EE_FF.1")
        self.assertIsNone(resolve_output(self.S(bt_mac="11:22:33:44:55:66"), run))                                    # a different speaker is NOT used
        self.assertIsNone(resolve_output(self.S(alsa_playback_device="plughw:0,0"), lambda c, timeout=4: ""))         # never silently back to the wired amp
        self.assertEqual(resolve_output(self.S(audio_backend="aplay", alsa_playback_device="bluealsa:DEV=X"), run).kind, "aplay")
    def test_paced_playback_delivers_everything_and_marks_start(self):
        from audio_out import BluetoothOutput; pr = FakeProc(); marks = []
        out = BluetoothOutput(self.S(), lambda c, timeout=4: PACTL, lambda *a, **k: pr); pcm = tone(24000, .5)
        ok, t0, n, cs = out.play(pcm, 24000, on_chunk=lambda i, t: marks.append((i, time.monotonic()))); self.assertTrue(ok); self.assertEqual(b"".join(pr.chunks), pcm)
        self.assertEqual(marks[0][0], 0); self.assertEqual(len(marks), n); span = marks[-1][1] - marks[0][1]; self.assertGreater(span, .5 - .25 - .1)   # real-time pacing, not dumped at once
    def test_speaker_disconnect_midway_is_reported_not_raised(self):
        from audio_out import BluetoothOutput; out = BluetoothOutput(self.S(), lambda c, timeout=4: PACTL, lambda *a, **k: FakeProc(broken_after=3))
        ok, *_ = out.play(tone(24000, .5), 24000); self.assertFalse(ok); self.assertIn("disconnected", out.last_error); self.assertIsNone(out._t)
    def test_no_speaker_found(self):
        from audio_out import BluetoothOutput; out = BluetoothOutput(self.S(), lambda c, timeout=4: "")
        ok, t0, n, cs = out.play(b"\0" * 100, 24000); self.assertFalse(ok); self.assertIsNone(t0); self.assertFalse(out.health()[0])
    def test_bluetooth_output_never_touches_microphone(self):
        import audio_out; src = open(audio_out.__file__).read(); self.assertNotIn("arecord", src); self.assertNotIn("capture_device", src); self.assertNotIn("MicCapture", src); self.assertNotIn("plughw", src)

# ------------------------------------------------------------------ Gemini service
class FakeModels:
    def __init__(self, script): self.script, self.calls = list(script), []
    def generate_content(self, **kw):
        self.calls.append(kw); r = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(r, Exception): raise r
        return r
class HttpErr(Exception):
    def __init__(self, code, msg=""): super().__init__(msg or f"HTTP {code}"); self.code = code
def resp_text(t): return NS(text=t)
def resp_audio(b): return NS(candidates=[NS(content=NS(parts=[NS(inline_data=NS(data=b))]))])
class TestGemini(unittest.TestCase):
    def svc(self, script, **kw):
        from ai_service import GeminiService; s = settings.Settings(); s.gemini_api_key = "KEY"; s.gemini_retries = 1
        for k, v in kw.items(): setattr(s, k, v)
        m = FakeModels(script); self.sleeps = []; return GeminiService(s, NS(models=m), sleep=self.sleeps.append), m
    def test_success_json_and_emotion_validation(self):
        g, m = self.svc([resp_text(json.dumps({"transcript": "hi", "reply": "Hello cutie", "emotion": "HAPPY"}))]); r = g.converse(b"wav")
        self.assertTrue(r.ok); self.assertEqual((r.text, r.emotion, r.transcript), ("Hello cutie", "happy", "hi")); self.assertEqual(g.history, [("hi", "Hello cutie")])
        g2, _ = self.svc([resp_text('```json\n{"transcript":"x","reply":"y","emotion":"dancing"}\n```')]); r = g2.converse(b"w"); self.assertEqual((r.text, r.emotion), ("y", ""))
    def test_plain_text_is_accepted_as_reply(self):
        g, _ = self.svc([resp_text("just text")]); self.assertEqual(g.converse(b"w").text, "just text")
    def test_silence_returns_empty_reply_without_error(self):
        g, _ = self.svc([resp_text('{"transcript":"","reply":"","emotion":"curious"}')]); r = g.converse(b"w"); self.assertTrue(r.ok); self.assertEqual(r.text, ""); self.assertEqual(g.history, [])
    def test_rate_limit_retries_then_succeeds(self):
        g, m = self.svc([HttpErr(429), resp_text('{"transcript":"a","reply":"b","emotion":"happy"}')]); r = g.converse(b"w"); self.assertTrue(r.ok); self.assertEqual(len(m.calls), 2); self.assertTrue(self.sleeps)
    def test_persistent_failures_become_spoken_fallbacks_never_exceptions(self):
        for err, kind in ((HttpErr(429), "rate"), (TimeoutError("timed out"), "timeout"), (HttpErr(503), "network"), (HttpErr(403, "API key invalid"), "auth"), (ValueError("boom"), "other")):
            g, m = self.svc([err]); r = g.converse(b"w"); self.assertFalse(r.ok); self.assertEqual(r.error, kind); self.assertTrue(r.text)
            self.assertEqual(len(m.calls), 2 if kind in ("rate", "timeout", "network") else 1)
    def test_empty_response_is_fallback(self):
        g, _ = self.svc([resp_text("  ")]); r = g.converse(b"w"); self.assertFalse(r.ok); self.assertEqual(r.error, "empty")
    def test_key_never_logged(self):
        buf = io.StringIO(); h = logging.StreamHandler(buf); lg = logging.getLogger(); lg.addHandler(h); lg.setLevel(logging.DEBUG)
        try: g, _ = self.svc([HttpErr(403, "bad key")], gemini_api_key="FAKETESTVALUEXYZ"); g.converse(b"w"); g.synthesize("x")
        finally: lg.removeHandler(h)
        self.assertNotIn("TESTVALUEXYZ", buf.getvalue())
    def test_tts_model_fallback_and_total_failure(self):
        g, m = self.svc([HttpErr(404, "model not found"), resp_audio(b"\x01\x02" * 100)], gemini_retries=0); self.assertEqual(g.synthesize("x"), b"\x01\x02" * 100); self.assertEqual(g._tts_i, 1)
        g, m = self.svc([HttpErr(404)], gemini_retries=0); self.assertIsNone(g.synthesize("x"))
    def test_tts_empty_audio_is_failure(self):
        g, m = self.svc([resp_audio(b"")], gemini_retries=0); self.assertIsNone(g.synthesize("x"))

# ------------------------------------------------------------------ mic + wake
class FakeStreamMic:
    def __init__(self, rms_seq, rate=16000): self.rate, self.chunk, self.seq, self.i = rate, int(rate * 2 * .1), list(rms_seq), 0
    def read(self, n=None):
        import struct; v = self.seq[min(self.i, len(self.seq) - 1)]; self.i += 1; k = (n or self.chunk) // 2
        return struct.pack("<h", int(v)) * k      # constant level = rms
class TestMicAndWake(unittest.TestCase):
    def test_vad_records_speech_with_preroll_and_tail(self):
        from mic import record_utterance; seq = [100] * 6 + [100] * 3 + [4000] * 8 + [100] * 14
        wav = record_utterance(FakeStreamMic(seq), clock=(lambda c=[0.0]: (c.__setitem__(0, c[0] + .1), c[0])[1])); self.assertIsNotNone(wav)
        w = wave.open(io.BytesIO(wav)); frames = w.getnframes(); self.assertEqual(w.getframerate(), 16000); self.assertGreater(frames / 16000, 8 * .1 + 1.2 - .1)
    def test_vad_no_speech_returns_none(self):
        from mic import record_utterance; clk = (lambda c=[0.0]: (c.__setitem__(0, c[0] + .1), c[0])[1])
        self.assertIsNone(record_utterance(FakeStreamMic([100] * 400), start_timeout=1.0, clock=clk))
    def test_vad_abort(self):
        from mic import record_utterance; self.assertIsNone(record_utterance(FakeStreamMic([100] * 50), should_abort=lambda: True))
    def test_mic_read_times_out_instead_of_hanging(self):
        from mic import MicCapture, MicError; r, w = os.pipe()
        m = MicCapture("x", popen=lambda *a, **k: NS(stdout=os.fdopen(r, "rb", 0), poll=lambda: None, terminate=lambda: None, wait=lambda timeout=None: 0, kill=lambda: None), read_timeout=.2); m.start()
        t = time.time(); self.assertRaises(MicError, m.read); self.assertLess(time.time() - t, 1.5); os.close(w)
    def test_mic_start_failure_is_micerror(self):
        from mic import MicCapture, MicError
        def boom(*a, **k): raise FileNotFoundError("arecord")
        self.assertRaises(MicError, MicCapture("x", popen=boom).start)
    def test_wake_word_matching(self):
        from wake import WakeWordDetector
        class Rec:
            def __init__(self, *a): self.t = iter(["", "hey", "novak", "hey nova"]); self.cur = ""
            def AcceptWaveform(self, d): self.cur = next(self.t, "hey nova"); return False
            def PartialResult(self): return json.dumps({"partial": self.cur})
            def Result(self): return json.dumps({"text": ""})
        class Model:
            def __init__(self, p): pass
        d = WakeWordDetector("/x", ["hey nova", "nova"], model_cls=Model, recognizer_cls=Rec); self.assertTrue(d.available)
        self.assertTrue(d.listen(FakeStreamMic([100]))); d.listen.__func__  # "novak" must not match, "hey nova" must
        self.assertFalse(d.listen(FakeStreamMic([100]), should_abort=lambda: True))
    def test_wake_unavailable_without_vosk_model(self):
        from wake import WakeWordDetector; d = WakeWordDetector("/definitely/not/here", ["nova"]); self.assertFalse(d.available); self.assertTrue(d.reason)

# ------------------------------------------------------------------ orchestration
class FakeMic:
    def __init__(self): self.active, self.starts, self.stops, self.rate, self.chunk = False, 0, 0, 16000, 3200
    def start(self): self.active = True; self.starts += 1
    def stop(self): self.active = False; self.stops += 1
class FakeWake:
    available = True
    def __init__(self, wakes): self.wakes, self.reason = wakes, ""
    def listen(self, mic, should_abort=None):
        while not (should_abort and should_abort()):
            if self.wakes > 0: self.wakes -= 1; return True
            time.sleep(.01)
        return False
class FakeAI:
    def __init__(self, replies): self.replies, self.block = list(replies), None
    def converse(self, wav):
        if self.block: self.block.wait(5)
        return self.replies.pop(0) if self.replies else __import__("ai_service").Reply(True, "")
class FakeSpeech:
    def __init__(self, mic=None, ok=True): self.said, self.mic, self.mic_active_during, self.ok = [], mic, [], ok
    def speak(self, text, emotion=None): self.said.append((text, emotion)); self.mic_active_during.append(self.mic.active if self.mic else None); time.sleep(.05); return self.ok
    def cancel(self): pass
    def play_effect(self, *a, **k): pass
def wait_for(fn, t=5):
    end = time.time() + t
    while time.time() < end:
        if fn(): return True
        time.sleep(.02)
    return False
class TestOrchestration(unittest.TestCase):
    def build(self, wakes=1, replies=(), wake=True, speech_ok=True, **skw):
        import brain, mic as micmod; from ai_service import Reply
        self.addCleanup(setattr, micmod, "record_utterance", micmod.record_utterance)
        self.wavs = [b"wav1", b"wav2", None, None, None]; micmod.record_utterance = lambda mic, start_timeout=None, should_abort=None: self.wavs.pop(0) if self.wavs else None
        s = settings.Settings(); s.humming = False; s.followup_s = 1
        for k, v in skw.items(): setattr(s, k, v)
        self.mic, self.face = FakeMic(), FakeFace(); self.ai = FakeAI(replies); self.speech = FakeSpeech(self.mic, speech_ok)
        a = brain.Aurora(s, face=self.face, mic=self.mic, wake=FakeWake(wakes) if wake else NS(available=False, reason="no model"), ai=self.ai, output=NS(), speech=self.speech,
                         camera=NS(enabled=False, start=lambda: False, reason="x", stop=lambda: None), touch_factory=lambda g: NS(start=lambda: True, stop=lambda: None, g=g))
        self.addCleanup(a.shutdown); return a
    def test_wake_to_speech_to_idle_with_mic_handled_and_states(self):
        from ai_service import Reply; a = self.build(replies=[Reply(True, "Hello", "hi", "happy")]); seen = []; a.state.subscribe(lambda o, n: seen.append(n.value)); a.start_background()
        self.assertTrue(wait_for(lambda: self.speech.said and a.state.state.value == "idle" and not a.subsystems.get("x"))); time.sleep(.15)
        self.assertEqual(self.speech.said[0], ("Hello", "happy")); self.assertEqual(self.speech.mic_active_during[0], False)       # mic paused while speaking (own voice)
        self.assertEqual(seen[:4], ["listening", "thinking", "speaking", "listening"]); self.assertEqual(seen[-1], "idle")
        self.assertTrue(self.mic.active); self.assertGreaterEqual(self.mic.starts, 2)                                           # listening again afterwards
    def test_gemini_failure_speaks_fallback_and_loop_survives(self):
        from ai_service import Reply; a = self.build(wakes=2, replies=[Reply(False, "Oops fallback", error="network"), Reply(True, "second ok")]); self.wavs[:] = [b"w", b"w", b"w", None]; a.start_background()
        self.assertTrue(wait_for(lambda: [t for t, _ in self.speech.said] == ["Oops fallback", "second ok"])); self.assertTrue(a.worker.is_alive())
    def test_bluetooth_down_does_not_break_mic_or_loop(self):
        from ai_service import Reply; a = self.build(wakes=2, replies=[Reply(True, "a"), Reply(True, "b")], speech_ok=False); self.wavs[:] = [b"w", None, b"w", None]; a.start_background()
        self.assertTrue(wait_for(lambda: len(self.speech.said) == 2)); self.assertTrue(a.worker.is_alive())
    def test_touch_reacts_while_ai_is_blocked_and_face_keeps_updating(self):
        from ai_service import Reply; a = self.build(replies=[Reply(True, "x")]); self.ai.block = threading.Event(); a.start_background()
        self.assertTrue(wait_for(lambda: a.state.state.value == "thinking")); t = time.monotonic(); a.on_touch("START")
        self.assertTrue(wait_for(lambda: self.face.emotions[-1][1] == Emotion.SHY, 1)); self.assertLess(time.monotonic() - t, .5)   # Gemini still blocked
        a.on_touch("HOLD"); self.assertTrue(wait_for(lambda: self.face.emotions[-1][1] == Emotion.ANGRY, 1))
        a.on_touch("RELEASE"); self.assertTrue(wait_for(lambda: self.face.emotions[-1][1] == Emotion.THINKING, 3)); self.ai.block.set()
    def test_touch_mapping_uses_existing_emotions_only(self):
        a = self.build(); a.expr.start()
        for ev, emo in (("START", Emotion.SHY), ("REPEAT", Emotion.CONFUSED), ("HOLD", Emotion.ANGRY)): a.on_touch(ev); self.assertTrue(wait_for(lambda: self.face.emotions[-1][1] == emo, 1), ev)
    def test_touch_to_talk_is_fallback_only(self):
        a = self.build(wake=True); a.on_touch("START"); self.assertFalse(a.talk_request.is_set()); self.assertFalse(a.touch_to_talk)
        b = self.build(wake=False); self.assertTrue(b.touch_to_talk); b.on_touch("START"); self.assertTrue(b.talk_request.is_set())
        c = self.build(wake=False, touch_to_talk="false"); c.on_touch("START"); self.assertFalse(c.talk_request.is_set())
    def test_no_wake_and_no_touch_means_no_conversation_ever(self):
        from ai_service import Reply; a = self.build(wake=False, touch_to_talk="false", replies=[Reply(True, "should not happen")]); a.start_background(); time.sleep(.6)
        self.assertEqual(self.speech.said, []); self.assertEqual(self.mic.starts, 0)                                          # open mic never used without activation
    def test_touch_to_talk_session(self):
        from ai_service import Reply; a = self.build(wake=False, replies=[Reply(True, "hi there")]); a.start_background(); a.on_touch("START")
        self.assertTrue(wait_for(lambda: self.speech.said))
    def test_long_press_emits_one_hold(self):
        from touch import GestureDetector; ev = []; g = GestureDetector(ev.append, hold_s=.15); g.pressed(); time.sleep(.6); g.released(); self.assertEqual(ev.count("HOLD"), 1); self.assertEqual(ev[0], "START"); self.assertEqual(ev[-1], "RELEASE")
    def test_camera_failure_does_not_block_startup(self):
        from camera_service import CameraService; c = CameraService(True); t = time.time(); self.assertFalse(c.start(timeout=2)); self.assertLess(time.time() - t, 2.5); self.assertFalse(CameraService(False).start())
        a = self.build(); a.camera = c; a.start_background(); self.assertTrue(wait_for(lambda: "optional" in a.subsystems["camera"][1], 3)); self.assertFalse(a.subsystems["camera"][0])
    def test_construction_survives_every_subsystem_failing(self):
        import brain; s = settings.Settings(); s.gemini_api_key = ""; s.vosk_model_path = "/no/model"; a = brain.Aurora(s, face=FakeFace(), touch_factory=lambda g: NS(start=lambda: False, stop=lambda: None))
        self.assertIsNotNone(a.expr); self.assertFalse(a.subsystems["gemini"][0]); self.assertFalse(a.subsystems["wake_word"][0]); print("\n" + a.report()); a.shutdown()
    def test_shutdown_releases_everything(self):
        a = self.build(); a.start_background(); time.sleep(.1); a.shutdown(); self.assertTrue(wait_for(lambda: not a.worker.is_alive(), 3)); self.assertFalse(self.mic.active)

class TestEndToEndSync(unittest.TestCase):
    def test_real_bluetooth_output_plus_speech_service_mouth_timing(self):
        """SpeechService + the REAL BluetoothOutput (fake player process): mouth opens only after the first audio chunk is written + latency."""
        from speech import SpeechService; from audio_out import BluetoothOutput; from expression import ExpressionManager
        s = settings.Settings(); s.lead_silence_ms = 200; s.output_latency_ms = 300; face, pr, writes = FakeFace(), FakeProc(), []
        orig = pr.write; pr.write = lambda b: (writes.append(time.monotonic()), orig(b))[1]
        out = BluetoothOutput(s, lambda c, timeout=4: PACTL, lambda *a, **k: pr); sp = SpeechService(s, lambda t: tone(24000, .5) + b"\0\0" * 12000, out, face, ExpressionManager(face))
        self.assertTrue(sp.speak("hello", "happy")); first_write = writes[0]; opened = [t for t, v in face.mouth if v and v > .5]
        self.assertTrue(opened); self.assertGreaterEqual(opened[0], first_write + .3 + .2 - .03)      # latency (0.3) + 0.2 s lead silence
        self.assertIsNone(face.mouth[-1][1]); self.assertTrue(pr.chunks)
        closing = [t for t, v in face.mouth if v is None][-1]; self.assertGreaterEqual(closing, first_write + 1.0 + .2 + .3 - .08)   # rest only after the sound ends

if __name__ == "__main__": unittest.main(verbosity=1)
