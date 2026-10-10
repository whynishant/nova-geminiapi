"""5. Touch sensor events only.  python3 -m tools.check_touch   (touch / hold / tap 3x for 30 s)"""
import time
from tools._u import *
from touch import GestureDetector, TouchInput
s = settings.Settings(); print("5. touch GPIO%d" % s.touch_pin); seen = []
g = GestureDetector(lambda e: (seen.append(e), print("  event", e, time.strftime("%X"))), s.touch_hold_s, s.touch_repeat_count, s.touch_repeat_window_s, s.touch_debounce_s)
t = TouchInput(s.touch_pin, s.touch_debounce_s, g)
if not t.start(): fail("touch sensor not available (gpiozero/lgpio/GPIO17?)"); done("5_touch")
time.sleep(30); t.stop()
(ok if "START" in seen else fail)(f"events seen: {seen}")
done("5_touch")
