# CHANGES
| File | Status | Why |
|---|---|---|
| `face.py` | **modified (+8 lines)** | `set_mouth_audio(level)` + one branch in `_update`: mouth follows real audio; `None` restores the original talk animation. Diff vs `face_WORKING_BACKUP.py` is exactly these lines. |
| `animation.py`, `emotion.py`, `easing.py`, `config.py` | **unchanged** | approved visuals/VAD constants (config.py VAD values are now reused by `mic.py`) |
| `brain.py` | **replaced** | orchestration only. Original kept as `brain_ORIGINAL_GROQ_ELEVEN_REFERENCE.py` (read-only) plus all existing `*_BACKUP*` / `*before_vad*` files |
| `settings.py` | new | env/hardware/AI settings; secrets masked |
| `state.py` | new | single IDLE/LISTENING/THINKING/SPEAKING state |
| `expression.py` | new | arbitration: interaction state (baseline) vs touch reactions (overlays); uses only existing emotions |
| `touch.py` | new | TTP223 adapter + gesture logic (START once, HOLD once, REPEAT, RELEASE; debounce) |
| `mic.py` | new | single owner of the arecord/INMP441 stream + the original VAD recorder (moved) |
| `wake.py` | new | Vosk wake word; unavailable ⇒ touch-to-talk fallback; no open-mic loop |
| `ai_service.py` | new | Gemini (audio→JSON reply+emotion, TTS), timeouts/retries/error classes, fallbacks |
| `audio_out.py` | new | Bluetooth sink discovery, paced raw playback, disconnect handling, hum generator (moved) |
| `speech.py` | new | speech lifecycle, mouth timeline from real audio levels, overlap cancel |
| `camera_service.py` | new | optional camera, off by default, timeout-guarded |
| `tools/*` | new | hardware validation scripts |
| `tests/*` | new | 50 simulation tests |
| `requirements.txt`, `.env.example`, `run.sh`, `stop.sh`, `.gitignore` | new/updated | `groq`, `elevenlabs`, `python-dotenv` no longer needed |
| `..env.swp` | **not shipped** | empty vim swap file with an env-like name |
