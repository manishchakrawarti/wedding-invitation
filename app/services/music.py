"""An original, royalty-free background tune for video invitations, generated in code (no licence to worry about):
a tanpura-like drone on Sa–Pa with soft temple-bell notes in raag Bhupali (Sa Re Ga Pa Dha)."""
import io
import wave
from functools import lru_cache

import numpy as np

RATE = 44100
SA = 220.0  # A3 as Sa
BHUPALI = [1, 9 / 8, 5 / 4, 3 / 2, 5 / 3, 2]  # Sa Re Ga Pa Dha Sa'


def _tanpura(seconds: float) -> np.ndarray:
    """Plucked drone: Pa, Sa', Sa', Sa (low), each string ringing with its overtones, one pluck every 0.6 s."""
    n = int(seconds * RATE)
    out = np.zeros(n)
    strings = [SA * 3 / 4, SA, SA, SA / 2]
    t = np.arange(int(2.6 * RATE)) / RATE
    for i, start in enumerate(np.arange(0, seconds, 0.6)):
        f = strings[i % 4]
        tone = sum(np.sin(2 * np.pi * f * h * t) / h ** 1.3 for h in range(1, 9))
        tone *= np.exp(-t * 1.4) * 0.13
        a = int(start * RATE)
        b = min(a + len(t), n)
        out[a:b] += tone[: b - a]
    return out


def _bells(seconds: float, seed: int) -> np.ndarray:
    """Soft bell melody on the Bhupali scale, a note every 1.2 s, rising and falling gently."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    out = np.zeros(n)
    t = np.arange(int(3.0 * RATE)) / RATE
    step = 2
    for start in np.arange(1.2, seconds - 1.5, 1.2):
        step = int(np.clip(step + rng.choice([-1, 0, 1, 1, -2, 2]), 0, len(BHUPALI) - 1))
        f = SA * 2 * BHUPALI[step]
        bell = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) + 0.2 * np.sin(2 * np.pi * f * 5.4 * t))
        bell *= np.exp(-t * 2.2) * 0.16
        a = int(start * RATE)
        b = min(a + len(t), n)
        out[a:b] += bell[: b - a]
    return out


@lru_cache(maxsize=4)
def background_wav(seconds: float = 32.0, seed: int = 7) -> bytes:
    """16-bit mono WAV, faded in and out."""
    mix = _tanpura(seconds) + _bells(seconds, seed)
    fade = int(1.5 * RATE)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade * 2:] *= np.linspace(1, 0, fade * 2)
    mix = np.clip(mix / max(np.abs(mix).max(), 1e-9) * 0.8, -1, 1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((mix * 32767).astype("<i2").tobytes())
    return buf.getvalue()
