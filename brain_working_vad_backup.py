"""
AURA robot brain: TTP223 -> INMP441 -> Groq Whisper -> Groq LLM -> ElevenLabs -> MAX98357A.
Pygame runs only on the main thread; all AI/network/audio work runs in a worker thread.
"""
import os, time, wave, subprocess, tempfile, threading, random
from dotenv import load_dotenv
from groq import Groq
from elevenlabs.client import ElevenLabs
from gpiozero import Button
from emotion import Emotion
from face import FaceEngine
import config

load_dotenv(os.path.expanduser("~/robot_brain/.env"))

GROQ_API_KEY=os.getenv("GROQ_API_KEY","").strip()
ELEVEN_API_KEY=os.getenv("ELEVEN_API_KEY","").strip()
VOICE_ID=os.getenv("ELEVEN_VOICE_ID","").strip()
CAPTURE_DEVICE=os.getenv("ALSA_CAPTURE_DEVICE","plughw:2,0").strip()
PLAYBACK_DEVICE=os.getenv("ALSA_PLAYBACK_DEVICE","").strip()
SAMPLE_RATE=int(os.getenv("SAMPLE_RATE","16000"))
RECORD_SECONDS=float(os.getenv("RECORD_SECONDS","5"))
HUMMING_ENABLED=os.getenv("HUMMING_ENABLED","true").lower()=="true"
HUM_MIN=float(os.getenv("HUM_MIN_SECONDS","45"))
HUM_MAX=float(os.getenv("HUM_MAX_SECONDS","90"))

if not GROQ_API_KEY: raise RuntimeError("GROQ_API_KEY missing in .env")
if not ELEVEN_API_KEY: raise RuntimeError("ELEVEN_API_KEY missing in .env")
if not VOICE_ID: raise RuntimeError("ELEVEN_VOICE_ID missing in .env")

groq=Groq(api_key=GROQ_API_KEY)
eleven=ElevenLabs(api_key=ELEVEN_API_KEY)
face=FaceEngine()
touch=Button(17,pull_up=False,bounce_time=0.15)

PERSONA="""You are AURA, Adarsh's cute playful female companion robot.
Speak in natural casual Hinglish. You know Adarsh personally.
Be warm, expressive, slightly nakhre-wali and cute, but never overly long.
Normally answer in 1-3 short spoken sentences. Do not use emojis, markdown, or stage directions.
If Adarsh jokes/flirts/playfully teases you, respond playfully and shyly when appropriate."""
conversation=[{"role":"system","content":PERSONA}]

def speech_to_text(path):
    face.set_emotion(Emotion.THINKING)

    try:
        with open(path, "rb") as f:
            result = groq.audio.transcriptions.create(
                file=(os.path.basename(path), f.read()),
                model="whisper-large-v3-turbo",
                language="hi"
            )

        return (result.text or "").strip()

    except Exception as e:
        print("❌ Whisper error:", e)
        raise

def record_audio():
    """
    Adaptive voice recording.

    Flow:
      1. Microphone starts after touch.
      2. Calibrates room noise.
      3. Waits for actual speech.
      4. Keeps recording while speech continues.
      5. Ends after sustained silence.
      6. Returns a WAV file for Whisper.
    """
    face.set_emotion(Emotion.LISTENING)

    path = "/tmp/aura_input.wav"

    from array import array
    import math

    # We use arecord in raw PCM mode so Python can inspect
    # the microphone level continuously.
    cmd = [
        "arecord",
        "-q",
        "-D", CAPTURE_DEVICE,
        "-f", "S16_LE",
        "-c", "1",
        "-r", str(SAMPLE_RATE),
        "-t", "raw",
        "-"
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0
        )

        chunk_ms = 100
        chunk_size = int(SAMPLE_RATE * 2 * chunk_ms / 1000)

        # ------------------------------
        # 1. CALIBRATE ROOM NOISE
        # ------------------------------
        print("🎙️ Calibrating microphone...")

        calibration_chunks = max(
            1,
            int(config.VAD_CALIBRATION_SECONDS / (chunk_ms / 1000))
        )

        noise_levels = []

        for _ in range(calibration_chunks):
            data = process.stdout.read(chunk_size)

            if not data:
                raise RuntimeError("Microphone stopped producing audio.")

            samples = array("h", data)
            rms = math.sqrt(
              sum(sample * sample for sample in samples) / max(1, len(samples))
            )

            noise_levels.append(rms)

        noise_floor = max(
            sum(noise_levels) / len(noise_levels),
            config.VAD_MIN_RMS
        )

        speech_threshold = max(
            config.VAD_MIN_RMS,
            noise_floor * config.VAD_SPEECH_MULTIPLIER
        )

        print(
            f"🎧 Noise floor: {noise_floor:.0f} | "
            f"Speech threshold: {speech_threshold:.0f}"
        )

        # ------------------------------
        # 2. WAIT FOR SPEECH
        # ------------------------------
        print("👂 Waiting for you to speak...")

        start_wait = time.monotonic()

        audio_chunks = []
        speech_started = False
        speech_start_time = None
        silence_start = None

        pre_roll_chunks = max(
            1,
            int(config.VAD_PRE_ROLL_SECONDS / (chunk_ms / 1000))
        )

        pre_roll = []

        while True:

            data = process.stdout.read(chunk_size)

            if not data:
                raise RuntimeError("Microphone stopped producing audio.")

            samples = array("h", data)
            rms = math.sqrt(
               sum(sample * sample for sample in samples) / max(1, len(samples))
            )

            # Keep a small amount of audio before speech.
            pre_roll.append(data)

            if len(pre_roll) > pre_roll_chunks:
                pre_roll.pop(0)

            # --------------------------------
            # SPEECH DETECTED
            # --------------------------------
            if rms >= speech_threshold:

                if not speech_started:
                    speech_started = True
                    speech_start_time = time.monotonic()

                    audio_chunks.extend(pre_roll)

                    print("🗣️ Speech detected...")

                audio_chunks.append(data)

                # Voice is active, so reset silence timer.
                silence_start = None

            # --------------------------------
            # SILENCE AFTER SPEECH
            # --------------------------------
            elif speech_started:

                audio_chunks.append(data)

                if silence_start is None:
                    silence_start = time.monotonic()

                silence_duration = (
                    time.monotonic() - silence_start
                )

                if (
                    silence_duration
                    >= config.VAD_END_SILENCE_SECONDS
                    and (
                        time.monotonic() - speech_start_time
                    ) >= config.VAD_MIN_SPEECH_SECONDS
                ):
                    print("🔇 Speech finished.")
                    break

            # --------------------------------
            # NO SPEECH YET
            # --------------------------------
            else:

                if (
                    time.monotonic() - start_wait
                    >= config.VAD_START_TIMEOUT_SECONDS
                ):
                    print("⏱️ No speech detected.")
                    break

            # --------------------------------
            # SAFETY LIMIT
            # --------------------------------
            if speech_started and (
                time.monotonic() - speech_start_time
                >= config.VAD_MAX_RECORD_SECONDS
            ):
                print("⏱️ Maximum recording time reached.")
                break

        # ------------------------------
        # STOP MICROPHONE
        # ------------------------------
        process.terminate()

        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        # ------------------------------
        # NO SPEECH
        # ------------------------------
        if not audio_chunks:
            raise RuntimeError("No speech detected.")

        # ------------------------------
        # WRITE WAV FILE
        # ------------------------------
        pcm_data = b"".join(audio_chunks)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_data)

        return path

    except Exception:
        try:
            process.terminate()
        except Exception:
            pass
        raise

def get_reply(text):
    face.set_emotion(Emotion.THINKING)

    conversation.append({
        "role": "user",
        "content": text
    })

    try:
        response = groq.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=conversation[-12:],
            max_completion_tokens=220,
            reasoning_effort="low"
        )

        reply = (response.choices[0].message.content or "").strip()

        if not reply:
            reply = "Hmm... ek second, main soch rahi hoon."

    except Exception as e:
        print("❌ Groq brain error:", e)
        reply = "Oops, mera brain thoda confuse ho gaya. Ek baar phir bolo na."

    conversation.append({
        "role": "assistant",
        "content": reply
    })

    return reply


def speak(text):
    face.set_emotion(Emotion.TALKING)
    face.set_talking_level(0.6)

    output_file = "/tmp/aura_reply.mp3"

    try:
        audio = eleven.text_to_speech.convert(
            voice_id=VOICE_ID,
            text=text,
            model_id="eleven_multilingual_v2"
        )

        with open(output_file, "wb") as f:
            f.write(b"".join(audio))

        cmd = ["mpg123", "-q"]

        if PLAYBACK_DEVICE:
            cmd += ["-a", PLAYBACK_DEVICE]

        cmd += [output_file]

        subprocess.run(
            cmd,
            check=True,
            timeout=45
        )

    except Exception as e:
        print("❌ ElevenLabs/playback error:", e)

    finally:
        face.set_talking_level(0)
        face.set_emotion(Emotion.IDLE)


def make_hum_wav(path):
    import math
    import struct

    sample_rate = 48000
    duration = 1.8

    notes = [
        220, 247, 262,
        247, 220, 196,
        220
    ]

    frames = []

    total_samples = int(sample_rate * duration)

    for i in range(total_samples):

        t = i / sample_rate

        note_index = min(
            len(notes) - 1,
            int(t / (duration / len(notes)))
        )

        note = notes[note_index]

        envelope = min(
            1.0,
            t / 0.15,
            (duration - t) / 0.2
        )

        sample = int(
            0.10 *
            envelope *
            (
                math.sin(2 * math.pi * note * t)
                +
                0.25 * math.sin(4 * math.pi * note * t)
            )
            * 32767
        )

        frames.append(
            struct.pack("<h", sample)
        )

    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))


def hum_once():
    if not HUMMING_ENABLED:
        return

    face.set_emotion(Emotion.HUMMING)
    face.set_talking_level(0.25)

    path = "/tmp/aura_hum.wav"

    try:
        make_hum_wav(path)

        cmd = ["aplay", "-q"]

        if PLAYBACK_DEVICE:
            cmd += ["-D", PLAYBACK_DEVICE]

        cmd += [path]

        subprocess.run(
            cmd,
            check=False,
            timeout=5
        )

    except Exception as e:
        print("❌ Humming error:", e)

    finally:
        face.set_talking_level(0)
        face.set_emotion(Emotion.IDLE)

def ai_loop():
    next_hum=time.monotonic()+random.uniform(HUM_MIN,HUM_MAX)
    print("Touch the sensor to talk.")
    while True:
        if touch.is_pressed:
            time.sleep(.15)
            print("\n👆 Touch detected!\n🎙️ Listening...")
            try:
                path=record_audio()
                print("✅ Recording complete.\n🧠 Converting speech to text...")
                text=speech_to_text(path)
                print("👤 You said:",text)
                if text:
                    reply=get_reply(text)
                    print("🤖 Robot:",reply)
                    low=text.lower()
                    if any(x in low for x in ["sharma","sharmao","sharm"]): face.set_emotion(Emotion.SHY)
                    elif any(x in low for x in ["love","pyaar","pyar"]): face.set_emotion(Emotion.LOVE)
                    elif "?" in text: face.set_emotion(Emotion.CURIOUS)
                    speak(reply)
                else:
                    face.set_emotion(Emotion.CURIOUS); time.sleep(.5); face.set_emotion(Emotion.IDLE)
            except Exception as e:
                print("❌ ERROR:",e)
                face.set_emotion(Emotion.ERROR); time.sleep(1); face.set_emotion(Emotion.IDLE)
            while touch.is_pressed: time.sleep(.05)
            # Tiny cute "shy" after interaction, then settle back to idle.
            face.set_emotion(Emotion.SHY)
            time.sleep(0.45)
            face.set_emotion(Emotion.IDLE)
            next_hum=time.monotonic()+random.uniform(HUM_MIN,HUM_MAX)
        elif time.monotonic()>=next_hum:
            hum_once(); next_hum=time.monotonic()+random.uniform(HUM_MIN,HUM_MAX)
        time.sleep(.03)

def main():
    face.start()
    worker=threading.Thread(target=ai_loop,daemon=True)
    worker.start()
    print("\n====================================")
    print("       AURA ROBOT IS READY")
    print("====================================\n")
    try: face.run()
    except KeyboardInterrupt: pass
    finally: face.stop()

if __name__=="__main__": main()
