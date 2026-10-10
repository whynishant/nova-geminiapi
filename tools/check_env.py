"""1. python + dependencies + config (no secrets printed).  python3 -m tools.check_env"""
import importlib, shutil, sys
from tools._u import *
print("1. environment"); (ok if sys.version_info >= (3, 9) else fail)(f"python {sys.version.split()[0]}")
for m, need in (("pygame", 1), ("gpiozero", 1), ("google.genai", 1), ("vosk", 0), ("lgpio", 0)):
    try: importlib.import_module(m); ok(m)
    except Exception as e: (fail if need else warn)(f"{m}: {e}" + ("  (wake word falls back to touch-to-talk)" if m == "vosk" else ""))
for b in ("arecord", "paplay", "pactl", "bluetoothctl"): (ok if shutil.which(b) else warn)(f"{b} " + ("found" if shutil.which(b) else "NOT found"))
s = settings.Settings(); print("  settings:", s)
for p in s.validate(): fail(p)
import os; (ok if os.path.isdir(s.vosk_model_path) else warn)(f"vosk model dir {s.vosk_model_path}")
done("1_env")
