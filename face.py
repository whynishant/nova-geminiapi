import math, random, sys, threading, time
import pygame
import pygame.gfxdraw
import config
from easing import ease_towards, clamp
from emotion import Emotion, get as get_emotion_params
from animation import Blinker, IdleBehaviour, TalkAnimator

class FaceEngine:
    """Main-thread Pygame renderer. All public setters are thread-safe."""
    def __init__(self):
        self._lock=threading.Lock()
        self._emotion=Emotion.IDLE; self._talking_level=0.0; self._gaze=None
        self._running=False; self._armed=False
        self._blinker=Blinker(); self._idle=IdleBehaviour(); self._talker=TalkAnimator()
        self._left=[1.,0.,0.,0.,1.,1.]; self._right=[1.,0.,0.,0.,1.,1.]
        self._mouth_curve=0.; self._mouth_open=0.; self._blush=0.; self._bounce=0.; self._sparkle=0.
        self._hearts=[]; self._screen=None; self._clock=None; self._w=config.FALLBACK_WIDTH; self._h=config.FALLBACK_HEIGHT
        self._params=get_emotion_params(Emotion.IDLE)
        self._mouth_audio=None   # NOVA extension: real speech loudness 0..1, or None = original random talk animation

    def start(self):
        with self._lock: self._armed=True; self._running=True
    def stop(self):
        with self._lock: self._running=False
    def set_emotion(self, emotion):
        if isinstance(emotion,str):
            try: emotion=Emotion(emotion.lower())
            except ValueError: return
        with self._lock: self._emotion=emotion
        if emotion not in (Emotion.IDLE,Emotion.SLEEPING): self._idle.notify_active()
    def get_emotion(self):
        with self._lock: return self._emotion
    def set_talking_level(self, level):
        with self._lock: self._talking_level=clamp(float(level),0,1)
    def set_mouth_audio(self, level):
        """NOVA extension. level 0..1 follows the real speech signal; None restores the original behaviour. Thread-safe, non-blocking."""
        with self._lock: self._mouth_audio=None if level is None else clamp(float(level),0,1)
    def look_left(self): self._set_gaze(-.6,0)
    def look_right(self): self._set_gaze(.6,0)
    def look_up(self): self._set_gaze(0,-.5)
    def look_down(self): self._set_gaze(0,.5)
    def look_center(self):
        with self._lock: self._gaze=None
    def _set_gaze(self,x,y):
        with self._lock: self._gaze=(x,y)

    def run(self):
        with self._lock:
            if not self._armed: raise RuntimeError("call face.start() before face.run()")
        pygame.init()
        info=pygame.display.Info()
        self._w=info.current_w or config.FALLBACK_WIDTH; self._h=info.current_h or config.FALLBACK_HEIGHT
        flags=pygame.FULLSCREEN if config.FULLSCREEN else 0
        try:
            self._screen=pygame.display.set_mode((self._w,self._h),flags)
        except pygame.error:
            self._w=config.FALLBACK_WIDTH; self._h=config.FALLBACK_HEIGHT
            self._screen=pygame.display.set_mode((self._w,self._h))
        pygame.display.set_caption("AURA")
        pygame.mouse.set_visible(False); self._clock=pygame.time.Clock()
        last=time.monotonic()
        try:
            while True:
                with self._lock: running=self._running
                if not running: break
                now=time.monotonic(); dt=min(now-last,.05); last=now
                for e in pygame.event.get():
                    if e.type==pygame.QUIT: self.stop()
                    elif e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE: self.stop()
                self._update(dt); self._draw(); pygame.display.flip(); self._clock.tick(config.TARGET_FPS)
        finally: pygame.quit()

    def _update(self,dt):
        with self._lock: emotion=self._emotion; level=self._talking_level; gaze=self._gaze; audio=self._mouth_audio
        p=get_emotion_params(emotion); self._params=p
        if gaze is not None: gx,gy=gaze
        elif p.gaze_x or p.gaze_y: gx,gy=p.gaze_x,p.gaze_y
        else: gx,gy=self._idle.update()
        closed=self._blinker.update(0 if emotion==Emotion.SLEEPING else p.blink_rate_mul)
        target_open=p.eye_open*(1-closed)
        for eye,left in ((self._left,True),(self._right,False)):
            asym=.15 if p.asymmetric and left else (-.05 if p.asymmetric else 0)
            wink=(self._blinker.wink_eye=="left" and left) or (self._blinker.wink_eye=="right" and not left)
            vals=(0 if wink else target_open,p.eye_squint,clamp(gx+asym,-1,1),clamp(gy,-1,1),p.eye_width_mul,p.eye_height_mul)
            for i,(cur,tgt,speed) in enumerate(zip(eye,vals,[config.EASE_SPEED_LIDS,config.EASE_SPEED_EYES,config.EASE_SPEED_GAZE,config.EASE_SPEED_GAZE,config.EASE_SPEED_EYES,config.EASE_SPEED_EYES])):
                eye[i]=ease_towards(cur,tgt,speed,dt)
        if audio is not None: open_target=.92*audio**.9      # mouth follows the actual audio being played
        elif emotion in (Emotion.TALKING,Emotion.HUMMING):
            self._talker.set_level(max(level,.35)); shape,lvl=self._talker.update()
            open_target={"closed":.05,"slightly_open":.25,"medium_open":.5,"wide_open":.85,"small_smile":.15}.get(shape,.3)*(.6+.4*lvl)
        else: open_target=p.mouth_open
        self._mouth_open=ease_towards(self._mouth_open,open_target,config.EASE_SPEED_MOUTH,dt)
        curve=p.mouth_curve+(.3 if self._idle.wants_smile and emotion==Emotion.IDLE else 0)
        self._mouth_curve=ease_towards(self._mouth_curve,curve,config.EASE_SPEED_MOUTH,dt)
        self._blush=ease_towards(self._blush,p.blush,config.EASE_SPEED_MOUTH,dt)
        self._bounce+=dt*(1.4+p.bounce); self._sparkle+=dt*3
        if p.heart and random.random()<dt*1.5: self._hearts.append([random.uniform(-1,1),0,0])
        for h in self._hearts: h[2]+=dt
        self._hearts=[h for h in self._hearts if h[2]<1.6]

    def _draw(self):
        s=self._screen; s.fill(config.COLOR_BG)
        by=math.sin(self._bounce)*self._h*.006*self._params.bounce
        ew=self._w*config.EYE_WIDTH_FRAC; eh=self._h*config.EYE_HEIGHT_FRAC; gap=self._w*config.EYE_GAP_FRAC
        cy=self._h*config.EYE_Y_FRAC+by; lx=self._w/2-gap/2-ew/2; rx=self._w/2+gap/2+ew/2
        self._draw_eye(lx,cy,ew,eh,self._left); self._draw_eye(rx,cy,ew,eh,self._right)
        if self._blush>.01: self._draw_blush(lx,rx,cy,eh)
        if self._params.sparkle: self._draw_sparkles(lx,rx,cy,eh)
        for h in self._hearts: self._draw_heart(h)
        self._draw_mouth(self._w/2,self._h*config.MOUTH_Y_FRAC+by,self._w*config.MOUTH_WIDTH_FRAC,self._h*config.MOUTH_HEIGHT_FRAC)

    def _draw_eye(self,cx,cy,bw,bh,state):
        op,sq,gx,gy,wm,hm=state; w=bw*wm; h=bh*hm*(1-.6*sq); r=min(w,h)*.4
        rect=pygame.Rect(int(cx-w/2),int(cy-h/2),max(1,int(w)),max(1,int(h)))
        pygame.draw.rect(self._screen,config.COLOR_EYE_WHITE,rect,border_radius=int(r))
        px=cx+gx*w*config.MAX_PUPIL_OFFSET_FRAC; py=cy+gy*h*config.MAX_PUPIL_OFFSET_FRAC
        ir=max(1,int(h/2*config.IRIS_RADIUS_FRAC)); pr=max(1,int(h/2*config.PUPIL_RADIUS_FRAC)); hr=max(1,int(h/2*config.HIGHLIGHT_RADIUS_FRAC))
        pygame.gfxdraw.filled_circle(self._screen,int(px),int(py),ir,config.COLOR_EYE_IRIS)
        pygame.gfxdraw.filled_circle(self._screen,int(px),int(py),pr,config.COLOR_EYE_PUPIL)
        pygame.gfxdraw.filled_circle(self._screen,int(px-ir*.35),int(py-ir*.35),hr,config.COLOR_EYE_HIGHLIGHT)
        lid=1-clamp(op,0,1)
        if lid>.01:
            lid_h=int(h*lid)
            pygame.draw.rect(self._screen,config.COLOR_LID,(int(cx-w*.52),int(cy-h/2),int(w*1.04),lid_h))

    def _draw_blush(self,lx,rx,cy,eh):
        surf=pygame.Surface((self._w,self._h),pygame.SRCALPHA); a=int(120*self._blush); r=max(2,int(eh*.28)); y=int(cy+eh*.55)
        for x in (lx,rx): pygame.gfxdraw.filled_circle(surf,int(x),y,r,(*config.COLOR_BLUSH,a))
        self._screen.blit(surf,(0,0))

    def _draw_sparkles(self,lx,rx,cy,eh):
        tw=(math.sin(self._sparkle)+1)/2; size=2+tw*2
        for x in (lx-eh*.7,rx+eh*.7):
            y=cy-eh*.6; pygame.draw.line(self._screen,config.COLOR_SPARKLE,(x-size*2,y),(x+size*2,y),2); pygame.draw.line(self._screen,config.COLOR_SPARKLE,(x,y-size*2),(x,y+size*2),2)

    def _draw_heart(self,p):
        ox,_,age=p; t=age/1.6; x=self._w/2+ox*self._w*.15; y=self._h*config.EYE_Y_FRAC-t*self._h*.25
        surf=pygame.Surface((40,40),pygame.SRCALPHA); a=int(255*(1-t)); col=(*config.COLOR_HEART,max(a,0)); sz=10
        pygame.gfxdraw.filled_circle(surf,15,16,5,col); pygame.gfxdraw.filled_circle(surf,25,16,5,col)
        pygame.gfxdraw.filled_polygon(surf,[(10,17),(30,17),(20,31)],col); self._screen.blit(surf,(x-20,y-20))

    def _draw_mouth(self,cx,cy,w,h):
        curve=clamp(self._mouth_curve,-1,1); op=clamp(self._mouth_open,0,1)
        if op<.06 and abs(curve)<.05:
            pygame.draw.line(self._screen,config.COLOR_MOUTH,(cx-w*.3,cy),(cx+w*.3,cy),4); return
        pts=[]
        for i in range(15):
            t=i/14; x=cx-w/2+w*t; y=cy-curve*h*.9*math.sin(math.pi*t); pts.append((x,y))
        if op<.08: pygame.draw.lines(self._screen,config.COLOR_MOUTH,False,pts,4); return
        mh=h*(.15+.85*op); top=[(x,y-mh*.5*op) for x,y in pts]; bottom=[(x,y+mh*.5) for x,y in pts]
        pygame.gfxdraw.filled_polygon(self._screen,top+bottom[::-1],config.COLOR_MOUTH)
        pygame.gfxdraw.aapolygon(self._screen,top+bottom[::-1],config.COLOR_MOUTH)
