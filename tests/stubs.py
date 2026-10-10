"""Lets the tests run on a dev machine without pygame / google-genai (they are stubbed ONLY here; the product code is untouched)."""
import sys, types
def install():
    if "pygame" not in sys.modules:
        pg = types.ModuleType("pygame"); pg.gfxdraw = types.ModuleType("pygame.gfxdraw"); sys.modules["pygame"], sys.modules["pygame.gfxdraw"] = pg, pg.gfxdraw
    if "google.genai" not in sys.modules:
        g = types.ModuleType("google"); ga = types.ModuleType("google.genai"); t = types.ModuleType("google.genai.types")
        class K:
            def __init__(self, *a, **k): self.a, self.k = a, k
        class Part(K):
            @staticmethod
            def from_bytes(data, mime_type): return Part(data=data, mime_type=mime_type)
        for n in ("Content", "GenerateContentConfig", "HttpOptions", "SpeechConfig", "VoiceConfig", "PrebuiltVoiceConfig"): setattr(t, n, type(n, (K,), {}))
        t.Part = Part; ga.types = t; g.genai = ga; ga.Client = K
        sys.modules.update({"google": g, "google.genai": ga, "google.genai.types": t})
