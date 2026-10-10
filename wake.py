"""Local wake word (Vosk, offline, keyword grammar). Reads the SAME MicCapture stream (no second device user).
If vosk or its model is missing, `available` is False and Aurora falls back to touch-to-talk. There is NO always-answering loop:
nothing is sent to Gemini unless the wake word (or the touch fallback) fired."""
import json, logging, os, re
log = logging.getLogger("aurora.wake")

class WakeWordDetector:
    def __init__(self, model_path, words, rate=16000, model_cls=None, recognizer_cls=None):
        self.words, self.rate, self.rec, self.reason = [w.lower() for w in words], rate, None, ""
        try:
            if model_cls is None:
                from vosk import Model, KaldiRecognizer, SetLogLevel
                SetLogLevel(-1); model_cls, recognizer_cls = Model, KaldiRecognizer
            if not os.path.isdir(model_path) and model_cls.__module__.startswith("vosk"): raise FileNotFoundError(f"vosk model not found at {model_path}")
            self._model, self._rc = model_cls(str(model_path)), recognizer_cls
            self.rec = self._rc(self._model, rate, json.dumps(self.words + ["[unk]"]))
        except Exception as e:
            self.reason = f"{type(e).__name__}: {e}"; log.warning("wake word unavailable: %s", self.reason)
    @property
    def available(self): return self.rec is not None
    def _hit(self, text): return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in self.words)
    def listen(self, mic, should_abort=None):
        """Blocks reading mic chunks. True = wake word heard, False = aborted. Raises MicError from the mic."""
        self.rec = self._rc(self._model, self.rate, json.dumps(self.words + ["[unk]"]))    # fresh decoder state
        while not (should_abort and should_abort()):
            data = mic.read(4000)
            text = json.loads(self.rec.Result())["text"] if self.rec.AcceptWaveform(data) else json.loads(self.rec.PartialResult())["partial"]
            if text and self._hit(text): log.info("wake word heard"); return True
        return False
