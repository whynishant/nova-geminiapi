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

def record_audio():
    face.set_emotion(Emotion.LISTENING)
    path="/tmp/aura_input.wav"
    cmd=["arecord","-q","-D",CAPTURE_DEVICE,"-f","S16_LE","-c","1","-r",str(SAMPLE_RATE),"-t","wav","-d",str(int(RECORD_SECONDS)),path]
    try:
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=RECORD_SECONDS+5)
    except Exception as e:
        raise RuntimeError(f"Microphone recording failed: {e}")
    return path

def speech_to_text(path):
    face.set_emotion(Emotion.THINKING)
    with open(path,"rb") as f:
        r=groq.audio.transcriptions.create(file=(os.path.basename(path),f.read()),model="whisper-large-v3-turbo",language="hi")
    return (r.text or "").strip()

def get_reply(text):
    face.set_emotion(Emotion.THINKING)
    conversation.append({"role":"user","content":text})
    try:
        r=groq.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=conversation[-12:],
            max_completion_tokens=220,
            reasoning_effort="low",
            temperature=0.7,
        )
        reply=(r.choices[0].message.content or "").strip()
        if not reply:
            reply="Hmm... ek second, main soch rahi hoon."
    except Exception as e:
        print("Groq error:",e)
        reply="Oops, mera brain thoda confuse ho gaya. Ek baar phir bolo na."
    conversation.append({"role":"assistant","content":reply})
    return reply

def speak(text):
    face.set_emotion(Emotion.TALKING)
    face.set_talking_level(.6)
    out="/tmp/aura_reply.mp3"
    try:
        audio=eleven.text_to_speech.convert(voice_id=VOICE_ID,text=text,model_id="eleven_multilingual_v2")
        with open(out,"wb") as f: f.write(b"".join(audio))
        cmd=["mpg123","-q"]
        if PLAYBACK_DEVICE: cmd += ["-a",PLAYBACK_DEVICE]
        cmd += [out]
        subprocess.run(cmd,check=True,timeout=45)
    except Exception as e:
        print("ElevenLabs/playback error:",e)
    finally:
        face.set_talking_level(0)
        face.set_emotion(Emotion.IDLE)

def make_hum_wav(path):
    # Short, gentle synthetic hum: local audio, no API call.
    import math, struct
    sr=48000; dur=1.8; notes=[220,247,262,247,220,196,220]
    frames=[]
    for i in range(int(sr*dur)):
        t=i/sr; note=notes[min(len(notes)-1,int(t/(dur/len(notes))))]
        env=min(1,t/.15,(dur-t)/.2)
        sample=int(0.10*env*(math.sin(2*math.pi*note*t)+.25*math.sin(4*math.pi*note*t))*32767)
        frames.append(struct.pack("<h",sample))
    with wave.open(path,"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(b"".join(frames))

def hum_once():
    if not HUMMING_ENABLED: return
    face.set_emotion(Emotion.HUMMING); face.set_talking_level(.25)
    path="/tmp/aura_hum.wav"
    try:
        make_hum_wav(path)
        cmd=["aplay","-q"]
        if PLAYBACK_DEVICE: cmd += ["-D",PLAYBACK_DEVICE]
        cmd += [path]
        subprocess.run(cmd,check=False,timeout=5)
    finally:
        face.set_talking_level(0); face.set_emotion(Emotion.IDLE)

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
