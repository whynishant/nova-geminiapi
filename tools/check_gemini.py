"""4. Real Gemini: auth, model names, JSON conversation from audio, TTS.  python3 -m tools.check_gemini"""
import math, struct, time, wave, io
from tools._u import *
s = settings.Settings(); print("4. gemini (REAL API)")
if not s.gemini_api_key: fail("GEMINI_API_KEY empty"); done("4_gemini")
from ai_service import GeminiService
g = GeminiService(s)
try:
    names = {m.name.split("/")[-1] for m in g._c().models.list()}; ok(f"auth ok, {len(names)} models visible")
    for n in [s.gemini_model] + s.gemini_tts_models: (ok if n in names else warn)(f"model {n}: " + ("listed" if n in names else "NOT in list (set GEMINI_MODEL / GEMINI_TTS_MODEL in .env)"))
except Exception as e: fail(f"list models: {type(e).__name__}: {e}")
b = io.BytesIO()
with wave.open(b, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 20))) for i in range(16000)))   # 1 s of tone: no speech
t = time.time(); r = g.converse(b.getvalue()); print(f"  converse -> ok={r.ok} err={r.error!r} text={r.text[:60]!r} ({time.time()-t:.1f}s)")
(ok if r.ok or r.error in ("empty",) else fail)("request/response/JSON path")
t = time.time(); a = g.synthesize("Hello, I am Aura."); (ok if a and len(a) > 4800 else fail)(f"TTS {0 if not a else len(a)/48000:.1f}s audio in {time.time()-t:.1f}s via {s.gemini_tts_models[g._tts_i]}")
if a: open("/tmp/aurora_tts.raw", "wb").write(a); print("  play: paplay --raw --rate=24000 --channels=1 --format=s16le /tmp/aurora_tts.raw")
done("4_gemini")
