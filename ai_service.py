"""Gemini conversation + speech. The ONLY module that imports the Gemini SDK. Runs on the worker thread - never on the animation loop.
audio (WAV) -> Gemini -> {"transcript","reply","emotion"} (JSON) -> Gemini TTS -> raw PCM 24 kHz s16le.
Every failure becomes a spoken/logged fallback; nothing here raises into the orchestrator and no key is ever logged."""
import json, logging, re, time
from dataclasses import dataclass
from emotion import Emotion
log = logging.getLogger("aurora.ai")

PERSONA = """You are AURA, Adarsh's cute playful female companion robot.
Speak in natural casual Hinglish. You know Adarsh personally.
Be warm, expressive, slightly nakhre-wali and cute, but never overly long.
Normally answer in 1-3 short spoken sentences. Do not use emojis, markdown, or stage directions.
If Adarsh jokes/flirts/playfully teases you, respond playfully and shyly when appropriate."""
ALLOWED = ["happy", "excited", "curious", "shy", "surprised", "confused", "sad", "angry", "love", "laughing", "celebrating", "success"]
SYSTEM = (PERSONA + "\n\nThe user's message arrives as AUDIO. Reply ONLY with a JSON object: "
          '{"transcript": "<what the user said, in their language>", "reply": "<your short spoken reply>", "emotion": "<one of: ' + ", ".join(ALLOWED) + '>"}. '
          'If the audio has no intelligible speech, return {"transcript": "", "reply": "", "emotion": "curious"}.')
FALLBACK = {"network": "Oops, mera brain thoda confuse ho gaya. Ek baar phir bolo na.", "timeout": "Oops, mera brain thoda confuse ho gaya. Ek baar phir bolo na.",
            "rate": "Thoda ruko na, abhi main bahut busy hoon. Thodi der baad phir bolna.", "auth": "Mujhe mera Gemini key accept nahi ho raha. Adarsh, ek baar check karo na.",
            "empty": "Hmm... ek second, main soch rahi hoon.", "other": "Oops, mera brain thoda confuse ho gaya. Ek baar phir bolo na."}

@dataclass
class Reply:
    ok: bool; text: str = ""; transcript: str = ""; emotion: str = ""; error: str = ""

class AIError(Exception):
    def __init__(self, kind, cause=None): super().__init__(f"{kind}: {cause}"); self.kind, self.cause = kind, cause

def classify(e):
    if isinstance(e, AIError): return e.kind
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    msg = (type(e).__name__ + " " + str(e)).lower()
    if code == 429 or "429" in msg or "resource_exhausted" in msg or "rate" in msg and "limit" in msg: return "rate"
    if code in (401, 403) or "api key" in msg or "permission_denied" in msg: return "auth"
    if isinstance(e, TimeoutError) or "timeout" in msg or "timed out" in msg: return "timeout"
    if (isinstance(code, int) and code >= 500) or "unavailable" in msg or "connection" in msg or "network" in msg or "dns" in msg: return "network"
    return "other"

def parse_reply(raw):
    t = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M).strip()
    try: d = json.loads(t)
    except ValueError: return ("", t, "") if t else ("", "", "")
    if not isinstance(d, dict): return "", t, ""
    em = str(d.get("emotion", "")).lower().strip()
    return str(d.get("transcript", "")).strip(), str(d.get("reply", "")).strip(), em if em in ALLOWED else ""

class GeminiService:
    def __init__(self, s, client=None, sleep=time.sleep):
        self.s, self._client, self.sleep, self.history, self._tts_i = s, client, sleep, [], 0
    def _c(self):
        if self._client is None:
            from google import genai
            from google.genai import types
            self._client = genai.Client(api_key=self.s.gemini_api_key, http_options=types.HttpOptions(timeout=int(self.s.gemini_timeout_s * 1000)))
        return self._client
    def _retry(self, fn):
        for attempt in range(self.s.gemini_retries + 1):
            try: return fn()
            except Exception as e:
                kind = classify(e)
                if isinstance(e, AIError) and kind == "empty": raise
                if kind in ("rate", "timeout", "network") and attempt < self.s.gemini_retries:
                    log.warning("gemini %s (attempt %d) - retrying", kind, attempt + 1); self.sleep(1.5 * (attempt + 1)); continue
                raise AIError(kind, e)
    def converse(self, wav: bytes) -> Reply:
        def call():
            from google.genai import types
            contents = [types.Content(role=r, parts=[types.Part(text=t)]) for u, a in self.history[-6:] for r, t in (("user", u), ("model", a))]
            contents.append(types.Content(role="user", parts=[types.Part.from_bytes(data=wav, mime_type="audio/wav"), types.Part(text="(Reply to the audio above as AURA, in the required JSON.)")]))
            r = self._c().models.generate_content(model=self.s.gemini_model, contents=contents, config=types.GenerateContentConfig(
                system_instruction=SYSTEM, response_mime_type="application/json", max_output_tokens=400, temperature=0.9))
            if not (r.text or "").strip(): raise AIError("empty")
            return r.text
        try: raw = self._retry(call)
        except AIError as e:
            log.error("gemini failed: %s", e.kind); return Reply(False, FALLBACK.get(e.kind, FALLBACK["other"]), error=e.kind)
        transcript, text, emotion = parse_reply(raw)
        if not text: return Reply(True, "", transcript, emotion or "curious")        # nothing intelligible: caller shows curiosity, no speech
        self.history.append((transcript or "(audio)", text)); self.history[:] = self.history[-12:]
        return Reply(True, text, transcript, emotion)
    def synthesize(self, text):
        """-> raw PCM s16le @24 kHz bytes, or None (logged). Tries the configured TTS models in order."""
        from google.genai import types
        for i in range(self._tts_i, len(self.s.gemini_tts_models)):
            def call():
                r = self._c().models.generate_content(model=self.s.gemini_tts_models[i], contents=self.s.tts_style + text, config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.s.gemini_voice)))))
                data = r.candidates[0].content.parts[0].inline_data.data
                if not data: raise AIError("empty")
                return data
            try: data = self._retry(call); self._tts_i = i; return bytes(data)
            except Exception as e: log.warning("TTS model %s failed: %s", self.s.gemini_tts_models[i], getattr(e, "kind", type(e).__name__))
        return None
