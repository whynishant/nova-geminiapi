"""3. Bluetooth speaker only (independent of the mic).  python3 -m tools.check_bt_audio"""
import subprocess
from tools._u import *
from audio_out import BluetoothOutput, _run
import math, struct
s = settings.Settings(); print("3. bluetooth output")
print("  paired/known devices:\n" + "\n".join("    " + l for l in _run(["bluetoothctl", "devices"]).splitlines()) )
print("  sinks:\n" + "\n".join("    " + l for l in _run(["pactl", "list", "short", "sinks"]).splitlines()))
o = BluetoothOutput(s); good, label = o.health(); (ok if good else fail)(f"target: {label}")
if good:
    pcm = b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 24000))) for i in range(24000 * 2)); print("  playing 2 s tone - you should hear it from the speaker...")
    r, t0, n, cs = o.play(pcm, 24000); (ok if r else fail)(f"playback finished ok={r} chunks={n}" + ("" if r else f" error={o.last_error}"))
    print("  CONFIRM BY EAR. Mouth/sound offset is tuned with OUTPUT_LATENCY_MS (now %.0f)." % s.output_latency_ms)
print("  mic still alive? (arecord list)"); print("   ", _run(["arecord", "-l"]).replace("\n", "\n    "))
done("3_bluetooth")
