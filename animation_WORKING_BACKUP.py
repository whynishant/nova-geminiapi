import random, time
import config

class Blinker:
    def __init__(self):
        self._next = time.monotonic() + random.uniform(config.BLINK_MIN_INTERVAL, config.BLINK_MAX_INTERVAL)
        self._start=None; self._duration=config.BLINK_DURATION_NORMAL; self._closed=0.0; self.wink_eye=None
        self._double=False
    def force_blink(self, slow=False):
        self._start=time.monotonic()
        self._duration=config.BLINK_DURATION_SLOW if slow else config.BLINK_DURATION_NORMAL
    def update(self, rate_mul=1.0):
        now=time.monotonic()
        if rate_mul<=0: return self._closed
        if self._start is None and now>=self._next:
            self._double=random.random()<config.DOUBLE_BLINK_CHANCE
            self.wink_eye=random.choice(["left","right"]) if random.random()<config.ASYMMETRIC_WINK_CHANCE else None
            self.force_blink(random.random()<config.SLOW_BLINK_CHANCE)
            self._next=now+random.uniform(config.BLINK_MIN_INTERVAL,config.BLINK_MAX_INTERVAL)/max(rate_mul,.01)
        if self._start is not None:
            t=(now-self._start)/self._duration
            if t>=1:
                self._closed=0; self._start=None; self.wink_eye=None
                if self._double:
                    self._double=False; self.force_blink()
            else:
                self._closed=1-abs(2*t-1)
        return self._closed

class IdleBehaviour:
    def __init__(self):
        self.x=self.y=0.0; self.next=time.monotonic()+random.uniform(3,8); self.wants_smile=False; self.last_active=time.monotonic()
    def notify_active(self): self.last_active=time.monotonic()
    def update(self):
        now=time.monotonic()
        if now>=self.next:
            self.x=random.uniform(-.5,.5); self.y=random.uniform(-.25,.25)
            self.wants_smile=random.random()<config.IDLE_SMILE_CHANCE
            self.next=now+random.uniform(config.IDLE_LOOK_MIN_INTERVAL,config.IDLE_LOOK_MAX_INTERVAL)
        return self.x+random.uniform(-1,1)*config.IDLE_MICROMOVE_AMPLITUDE, self.y+random.uniform(-1,1)*config.IDLE_MICROMOVE_AMPLITUDE
    def is_sleepy(self): return time.monotonic()-self.last_active>config.SLEEPY_AFTER_SECONDS

class TalkAnimator:
    SHAPES=("closed","slightly_open","medium_open","wide_open","small_smile")
    def __init__(self): self.level=.5; self.shape="closed"; self.next=0
    def set_level(self, level): self.level=max(0,min(1,level))
    def update(self):
        now=time.monotonic()
        if now>=self.next:
            self.shape=random.choices(self.SHAPES, weights=[.15,.25,.3,.15,.15])[0]
            self.next=now+random.uniform(config.TALK_SHAPE_CHANGE_MIN,config.TALK_SHAPE_CHANGE_MAX)
        return self.shape,self.level
