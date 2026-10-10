# AURORA × NOVA (final build for the hackathon)

Aurora keeps its face, animations and hardware (INMP441, TTP223 on GPIO17). It gets NOVA's architecture and interaction model:
**wake word → Gemini → spoken reply on the Bluetooth speaker → mouth follows the real audio**, touch → expression, camera optional.

    idle (eyes) ──"Hey Nova"──> LISTENING (VAD, INMP441) ──> THINKING (Gemini, worker thread) ──> SPEAKING (Gemini TTS → Bluetooth, mouth = audio level) ──> follow-up window (5 s) ──> idle
    TTP223 touch (any time, independent): 1st touch = shy · 3 quick touches = confused · hold 2.5 s = angry · back to the current expression afterwards

## Install (on the Pi, in the SAME Python environment Aurora already used)
    cd ~/robot_brain                      # copy this folder there (keep your old one as a backup: mv ~/robot_brain ~/robot_brain_OLD)
    sudo apt install -y alsa-utils pulseaudio-utils bluez python3-lgpio
    pip install -r requirements.txt       # google-genai + vosk are the only new Python packages (add --break-system-packages only if Aurora was installed system-wide)
    cp .env.example .env && nano .env     # set GEMINI_API_KEY (and BT_SPEAKER_MAC)
    # wake word model (offline, 36 MB; without it Aurora automatically uses touch-to-talk):
    mkdir -p models && cd models && wget https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip && unzip vosk-model-small-en-in-0.4.zip && mv vosk-model-small-en-in-0.4 vosk-model && cd ..
Nothing here changes your audio stack, I2S/overlay settings or any system file. The INMP441 settings are untouched.

## Bluetooth speaker (one time)
    bluetoothctl                              # then:  power on · agent on · scan on · pair XX:XX:XX:XX:XX:XX · trust XX:XX:XX:XX:XX:XX · connect XX:XX:XX:XX:XX:XX · exit
Put the MAC in `.env` as `BT_SPEAKER_MAC`. Aurora finds the matching sink with `pactl` (PulseAudio/PipeWire) and plays through `paplay`; on a BlueALSA system it uses `aplay -D bluealsa:DEV=<MAC>`. It never falls back to the wired amplifier. If your system uses neither, tell me the output of `tools.check_bt_audio`.

## Validate on the Pi (in this order; each prints `RESULT … PASS/FAIL`)
    python3 -m tools.check_env            # deps, key present (never printed), paths
    python3 -m tools.check_mic            # INMP441 only
    python3 -m tools.check_bt_audio       # Bluetooth speaker only (mic untouched)
    python3 -m tools.check_gemini         # REAL API: auth, model names, JSON chat, TTS
    python3 -m tools.check_touch          # GPIO17 events
    python3 -m tools.demo_face_sync       # real face + real speaker: mouth/sound sync + touch reactions (ESC quits). Tune OUTPUT_LATENCY_MS here.

## Run / stop
    cd ~/robot_brain && ./run.sh          # = python3 brain.py   (startup prints which subsystems are OK/OFF)
    ./stop.sh                             # or Ctrl+C / ESC on the face window

## Demo flow
"Hey Nova, …" → eyes wake, listen, think, speak. Touch Aurora while idle/talking to see reactions. If the wake word is flaky in a noisy hall: `TOUCH_TO_TALK=true` in `.env` enables touch-to-talk **in addition** to the wake word.

## Honest limitations
* Everything below "Validate on the Pi" is **NOT hardware-tested yet**; see TEST_CHECKLIST.md.
* Model names (`gemini-3.6-flash`, TTS `gemini-3.8-flash-lite-tts`) are provisional; `check_gemini` lists what your key can use. Change in `.env`, no code edit.
* Wake word = Vosk keyword spotting with an English-India model; accuracy on "Hey Nova" in a loud room is untested. During follow-up (5 s after a reply) any speech is treated as the next question (`FOLLOWUP_SECONDS=0` disables).
* The microphone is paused while Aurora speaks (so it doesn't hear itself). This is deliberate, not caused by Bluetooth; there is no barge-in.
* Mouth sync = loudness of the real audio, delayed by `OUTPUT_LATENCY_MS` (Bluetooth latency varies per speaker; measure by eye with `demo_face_sync`). No visemes.
* Camera is off by default (`ENABLE_CAMERA=false`) and can never block startup.
* The old Groq/ElevenLabs path is kept only as `brain_ORIGINAL_GROQ_ELEVEN_REFERENCE.py`.
