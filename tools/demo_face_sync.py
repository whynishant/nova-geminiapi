"""6. Face + mouth sync + touch reactions WITHOUT Gemini: plays a tone-modulated test phrase through the Bluetooth speaker while the REAL face renders.
   python3 -m tools.demo_face_sync     (ESC to quit; touch the sensor to see reactions)"""
import math, struct, threading, time
from tools._u import *
from face import FaceEngine
from emotion import Emotion
import brain
s = settings.Settings(); s.humming = False
rate = 24000; env = [0, .9, .3, 1, .1, .8, 0, 1, .5, 0]    # syllable-like bursts
pcm = b"".join(struct.pack("<h", int(9000 * env[min(9, i * 10 // (rate * 4))] * math.sin(2 * math.pi * 200 * i / rate))) for i in range(rate * 4))
class DemoAI:
    def converse(self, wav): return None
    def synthesize(self, text): return pcm
a = brain.Aurora(s, ai=DemoAI(), mic=None); a.speech = a.speech or __import__("speech").SpeechService(s, DemoAI().synthesize, a.output, a.face, a.expr)
def talk():
    time.sleep(2)
    while not a.stop_evt.is_set():
        a.state.set(brain.State.SPEAKING); print("speaking test phrase..."); print("played:", a.speech.speak("demo", "happy")); a.state.set(brain.State.IDLE); a.stop_evt.wait(5)
a.start_background(); threading.Thread(target=talk, daemon=True).start(); a.face.run(); a.shutdown()
