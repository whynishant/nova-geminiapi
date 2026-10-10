import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import settings; settings.load_env()
_f = []
def ok(m): print("  PASS  " + m)
def warn(m): print("  WARN  " + m)
def fail(m): _f.append(m); print("  FAIL  " + m)
def done(n):
    print(f"RESULT {n}: " + (f"FAIL ({len(_f)})" if _f else "PASS")); sys.exit(1 if _f else 0)
