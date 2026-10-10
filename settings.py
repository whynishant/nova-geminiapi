"""Runtime/hardware/AI settings (NOT the face look - that stays in config.py). Secrets only from the environment / .env.
Values keep the original Aurora defaults where they existed (capture device plughw:2,0, GPIO17, 16 kHz)."""
import os, pathlib
HERE = pathlib.Path(__file__).resolve().parent

def _parse_env_file(path):
    out = {}
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); out[k.strip()] = v.strip().strip('"').strip("'")
    return out

def load_env():
    """Loads (without overriding real env vars): $AURORA_ENV, ~/robot_brain/.env, ./.env. Returns the files used."""
    used = []
    for p in (os.environ.get("AURORA_ENV"), pathlib.Path.home() / "robot_brain" / ".env", HERE / ".env"):
        if p and pathlib.Path(p).is_file():
            for k, v in _parse_env_file(pathlib.Path(p)).items(): os.environ.setdefault(k, v)
            used.append(str(p))
    return used

def _s(n, d=""): return os.environ.get(n, d).strip()
def _f(n, d): 
    try: return float(os.environ.get(n, d))
    except ValueError: return float(d)
def _i(n, d): return int(_f(n, d))
def _b(n, d): return os.environ.get(n, str(d)).strip().lower() in ("1", "true", "yes", "on")

class Settings:
    SECRETS = ("gemini_api_key",)
    def __init__(self):
        self.gemini_api_key = _s("GEMINI_API_KEY")
        self.gemini_model = _s("GEMINI_MODEL", "gemini-3.6-flash")                 # provisional name (from NOVA config): verify with tools/check_gemini.py
        self.gemini_tts_models = [m for m in (_s("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts"), "gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview") if m]
        self.gemini_voice = _s("GEMINI_VOICE", "Kore")
        self.tts_style = _s("GEMINI_TTS_STYLE", "Say in a warm, cute, playful young voice: ")
        self.gemini_timeout_s = _f("GEMINI_TIMEOUT_S", 25); self.gemini_retries = _i("GEMINI_RETRIES", 1)
        self.tts_rate = 24000
        # microphone (INMP441 via ALSA - unchanged from the working Aurora build)
        self.capture_device = _s("ALSA_CAPTURE_DEVICE", "plughw:2,0"); self.sample_rate = _i("SAMPLE_RATE", 16000)
        # output (Bluetooth)
        self.bt_mac = _s("BT_SPEAKER_MAC").upper(); self.audio_backend = _s("AUDIO_BACKEND", "auto").lower()   # auto | paplay | aplay
        self.audio_sink = _s("AUDIO_SINK"); self.alsa_playback_device = _s("ALSA_PLAYBACK_DEVICE")
        self.output_latency_ms = _f("OUTPUT_LATENCY_MS", 350); self.lead_silence_ms = _f("OUTPUT_LEAD_SILENCE_MS", 400)
        # touch (TTP223)
        self.touch_pin = _i("TOUCH_PIN", 17); self.touch_debounce_s = _f("TOUCH_DEBOUNCE_S", 0.08)
        self.touch_hold_s = _f("TOUCH_HOLD_S", 2.5); self.touch_repeat_count = _i("TOUCH_REPEAT_COUNT", 3); self.touch_repeat_window_s = _f("TOUCH_REPEAT_WINDOW_S", 10)
        self.touch_first, self.touch_repeat, self.touch_hold = _s("TOUCH_EMOTION_FIRST", "shy"), _s("TOUCH_EMOTION_REPEAT", "confused"), _s("TOUCH_EMOTION_HOLD", "angry")
        self.touch_to_talk = _s("TOUCH_TO_TALK", "auto").lower()           # auto = only when wake word is unavailable | true | false
        # wake word
        self.wake_enabled = _b("ENABLE_WAKE_WORD", True); self.wake_words = [w.strip().lower() for w in _s("WAKE_WORDS", "hey nova,nova").split(",") if w.strip()]
        self.vosk_model_path = _s("VOSK_MODEL_PATH", str(pathlib.Path.home() / "robot_brain" / "models" / "vosk-model")); self.followup_s = _f("FOLLOWUP_SECONDS", 5)
        # misc
        self.enable_camera = _b("ENABLE_CAMERA", False)
        self.humming = _b("HUMMING_ENABLED", True); self.hum_min = _f("HUM_MIN_SECONDS", 45); self.hum_max = _f("HUM_MAX_SECONDS", 90)
    def validate(self):
        """Returns a list of problems (never includes secret values)."""
        return [] if self.gemini_api_key else ["GEMINI_API_KEY is empty (put it in ~/robot_brain/.env)"]
    def __repr__(self):
        d = {k: ("<set>" if (k in self.SECRETS and v) else v) for k, v in vars(self).items()}
        return "Settings(%s)" % ", ".join(f"{k}={v!r}" for k, v in d.items())
