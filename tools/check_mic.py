"""2. INMP441 only (no speaker, no Gemini).  python3 -m tools.check_mic"""
import time
from tools._u import *
from mic import MicCapture, MicError, record_utterance, rms_of
s = settings.Settings(); print("2. microphone", s.capture_device); m = MicCapture(s.capture_device, s.sample_rate)
try:
    m.start(); lv = [rms_of(m.read()) for _ in range(10)]; ok(f"capturing; ambient rms avg {sum(lv)/len(lv):.0f} (VAD_MIN_RMS={__import__('config').VAD_MIN_RMS})")
    print("  SPEAK NOW (10 s)..."); w = record_utterance(m, start_timeout=10)
    if w: open("/tmp/aurora_mic_test.wav", "wb").write(w); ok(f"speech captured {len(w)} bytes -> /tmp/aurora_mic_test.wav (play: aplay /tmp/aurora_mic_test.wav)")
    else: fail("no speech detected")
except MicError as e: fail(str(e))
finally: m.stop()
done("2_mic")
