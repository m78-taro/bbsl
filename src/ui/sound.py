"""提示音。

不用 Windows 的系统提示音：备份和还原会是同一个声音，听不出区别。
这里自己合成三个短音效，启动时写到临时目录里播放：
    save   往上走的两声
    load   往下走的两声
    error  低沉的两下

想换成自己的声音：在工具目录下建 sounds 文件夹，放 save.wav / load.wav / error.wav，有哪个就用哪个。
"""
import math
import os
import struct
import tempfile
import wave
import winsound

RATE = 44100
_paths = {}


def _tone(freq, dur, vol=0.32, shape="sine"):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        t = i / RATE
        env = min(1.0, t / 0.004) * math.exp(-t * 9)      # 4ms 淡入，之后自然衰减，听着像轻敲
        x = math.sin(2 * math.pi * freq * t)
        if shape == "sine":
            x += 0.25 * math.sin(4 * math.pi * freq * t)     # 加一点泛音，比纯正弦好听
            x /= 1.25
        else:
            x = math.copysign(min(1.0, abs(x) * 2.5), x)      # 削顶，听着发闷发涩，用在出错
        out.append(x * env * vol)
    return out


def _silence(dur):
    return [0.0] * int(RATE * dur)


def _write(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


def init(tool_dir):
    builtin = {
        "save": _tone(784, 0.09) + _tone(1175, 0.22),                       # G5 -> D6
        "load": _tone(1175, 0.09) + _tone(784, 0.22),                       # D6 -> G5
        "error": _tone(196, 0.12, 0.28, "buzz") + _silence(0.05) + _tone(196, 0.16, 0.28, "buzz"),
    }
    tmp = os.path.join(tempfile.gettempdir(), "bbsl_sounds")
    custom = os.path.join(tool_dir, "sounds")
    for kind, samples in builtin.items():
        mine = os.path.join(custom, f"{kind}.wav")
        if os.path.isfile(mine):
            _paths[kind] = mine
            continue
        try:
            os.makedirs(tmp, exist_ok=True)
            p = os.path.join(tmp, f"{kind}.wav")
            _write(p, samples)
            _paths[kind] = p
        except OSError:
            pass


def play(kind):
    """kind: save / load / error。异步播放，不卡界面。"""
    p = _paths.get(kind)
    try:
        if p:
            winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        else:
            winsound.MessageBeep()
    except RuntimeError:
        pass
