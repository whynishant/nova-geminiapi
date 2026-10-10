from dataclasses import dataclass
from enum import Enum

class Emotion(str, Enum):
    IDLE="idle"; LISTENING="listening"; THINKING="thinking"; TALKING="talking"
    HAPPY="happy"; EXCITED="excited"; CURIOUS="curious"; SHY="shy"
    SURPRISED="surprised"; CONFUSED="confused"; SAD="sad"; ANGRY="angry"
    LOVE="love"; SLEEPING="sleeping"; WAKING="waking"; LAUGHING="laughing"
    CELEBRATING="celebrating"; ERROR="error"; SUCCESS="success"; HUMMING="humming"

@dataclass
class EmotionParams:
    eye_open: float=1.0
    eye_squint: float=0.0
    eye_width_mul: float=1.0
    eye_height_mul: float=1.0
    brow_angle: float=0.0
    gaze_x: float=0.0
    gaze_y: float=0.0
    mouth_shape: str="neutral"
    mouth_curve: float=0.0
    mouth_open: float=0.0
    bounce: float=0.15
    blush: float=0.0
    sparkle: bool=False
    heart: bool=False
    asymmetric: bool=False
    blink_rate_mul: float=1.0

EMOTIONS = {
 Emotion.IDLE: EmotionParams(eye_open=.92, eye_squint=.05, mouth_curve=.15, bounce=.2),
 Emotion.LISTENING: EmotionParams(eye_open=1.05, mouth_shape="small", mouth_curve=.1, gaze_y=-.05, bounce=.1, blink_rate_mul=.7),
 Emotion.THINKING: EmotionParams(eye_open=.85, eye_squint=.1, mouth_shape="thoughtful", mouth_curve=-.05, gaze_x=.35, gaze_y=-.4, bounce=.15, asymmetric=True, blink_rate_mul=.8),
 Emotion.TALKING: EmotionParams(eye_open=1.0, eye_squint=.05, mouth_shape="talk", mouth_curve=.2, bounce=.25),
 Emotion.HAPPY: EmotionParams(eye_open=.6, eye_squint=.75, mouth_shape="smile", mouth_curve=.9, mouth_open=.35, bounce=.5, sparkle=True),
 Emotion.EXCITED: EmotionParams(eye_open=1.15, eye_squint=.15, mouth_shape="open_smile", mouth_curve=1, mouth_open=.6, bounce=.75, sparkle=True, blink_rate_mul=1.3),
 Emotion.CURIOUS: EmotionParams(eye_open=1.05, mouth_shape="small", mouth_curve=.2, gaze_x=.4, bounce=.2, asymmetric=True),
 Emotion.SHY: EmotionParams(eye_open=.55, eye_squint=.2, mouth_shape="tiny_smile", mouth_curve=.4, gaze_x=-.4, gaze_y=.35, bounce=.1, blush=.8, blink_rate_mul=1.1),
 Emotion.SURPRISED: EmotionParams(eye_open=1.4, eye_width_mul=1.08, mouth_shape="o_shape", mouth_open=.8, brow_angle=1, bounce=.3, blink_rate_mul=.5),
 Emotion.CONFUSED: EmotionParams(eye_open=.95, mouth_shape="wavy", mouth_curve=-.1, gaze_x=-.3, brow_angle=-.4, bounce=.15, asymmetric=True),
 Emotion.SAD: EmotionParams(eye_open=.65, mouth_shape="frown", mouth_curve=-.7, gaze_y=.3, brow_angle=-.6, bounce=.05, blink_rate_mul=.6),
 Emotion.ANGRY: EmotionParams(eye_open=.7, eye_squint=.3, mouth_shape="flat_frown", mouth_curve=-.5, brow_angle=-1, bounce=.1, blink_rate_mul=.5),
 Emotion.LOVE: EmotionParams(eye_open=.55, eye_squint=.8, mouth_shape="smile", mouth_curve=.85, bounce=.4, heart=True, sparkle=True),
 Emotion.SLEEPING: EmotionParams(eye_open=.04, mouth_shape="tiny_smile", mouth_curve=.05, bounce=.35, blink_rate_mul=0),
 Emotion.WAKING: EmotionParams(eye_open=.4, eye_squint=.1, mouth_shape="small", mouth_curve=.1, bounce=.15, blink_rate_mul=1.5),
 Emotion.LAUGHING: EmotionParams(eye_open=.35, eye_squint=.9, mouth_shape="open_smile", mouth_curve=1, mouth_open=.7, bounce=.9, sparkle=True, blink_rate_mul=1.4),
 Emotion.CELEBRATING: EmotionParams(eye_open=.5, eye_squint=.85, mouth_shape="open_smile", mouth_curve=1, mouth_open=.55, bounce=1, sparkle=True),
 Emotion.ERROR: EmotionParams(eye_open=.8, mouth_shape="wavy", mouth_curve=-.4, brow_angle=-.5, bounce=.1, asymmetric=True),
 Emotion.SUCCESS: EmotionParams(eye_open=.6, eye_squint=.7, mouth_shape="smile", mouth_curve=.8, bounce=.4, sparkle=True),
 Emotion.HUMMING: EmotionParams(eye_open=.75, eye_squint=.35, mouth_shape="hum", mouth_curve=.5, mouth_open=.25, bounce=.5, blink_rate_mul=.8),
}

def get(emotion):
    return EMOTIONS.get(emotion, EMOTIONS[Emotion.IDLE])
