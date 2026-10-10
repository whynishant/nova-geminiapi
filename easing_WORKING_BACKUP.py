import math

def lerp(a, b, t):
    return a + (b - a) * t

def ease_towards(current, target, speed, dt):
    t = 1.0 - math.exp(-speed * dt)
    return lerp(current, target, t)

def clamp(value, lo, hi):
    return max(lo, min(hi, value))
