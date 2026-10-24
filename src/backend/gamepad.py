"""Xbox 手柄（XInput）组合键。

手柄没法像键盘那样把按键拦下来，游戏一定也收得到，所以：
  - 至少要两个键的组合，单个键太容易和游戏操作撞上
  - 组合要按住 0.6 秒才触发，平时顺手按到不会误触
  - 必须正好是这几个键：多按了别的键（比如边跑边按）不算

PS 手柄暂不支持（没设备测）。用 Steam 输入或 DS4Windows 转成 Xbox 手柄的话也能用。
"""
import ctypes
import ctypes.wintypes as wt
import queue
import threading
import time

import keyspec


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", wt.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wt.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


# 规格名 -> 按键位；LT/RT 是模拟量，单独处理
BUTTONS = [
    ("pad_up", 0x0001), ("pad_down", 0x0002), ("pad_left", 0x0004), ("pad_right", 0x0008),
    ("pad_start", 0x0010), ("pad_back", 0x0020), ("pad_ls", 0x0040), ("pad_rs", 0x0080),
    ("pad_lb", 0x0100), ("pad_rb", 0x0200), ("pad_a", 0x1000), ("pad_b", 0x2000),
    ("pad_x", 0x4000), ("pad_y", 0x8000),
]
ORDER = ["pad_lb", "pad_rb", "pad_lt", "pad_rt", "pad_back", "pad_start", "pad_a", "pad_b", "pad_x", "pad_y",
         "pad_up", "pad_down", "pad_left", "pad_right", "pad_ls", "pad_rs"]
TRIGGER = 64          # 扳机按下超过 1/4 才算按下
HOLD = 0.6            # 组合要按住多久
POLL = 1 / 60
RESCAN = 1.0          # 没插的手柄位隔多久再看一次（XInput 查没插的位很慢，不能每帧查）


def _load_xinput():
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            dll = ctypes.WinDLL(name)
            fn = dll.XInputGetState
            fn.argtypes = [wt.DWORD, ctypes.POINTER(XINPUT_STATE)]
            fn.restype = wt.DWORD
            return fn
        except (OSError, AttributeError):
            continue
    return None


def build(names):
    return "+".join(n for n in ORDER if n in names)


def parse(spec):
    if not spec:
        return None
    parts = set(spec.split("+"))
    if not parts or any(p not in keyspec.PAD for p in parts):
        return None
    return frozenset(parts)


class Gamepad:
    """事件：("fire", 动作) / ("rec", 规格) / ("rec_bad", 原因)"""

    def __init__(self):
        self.events = queue.Queue()
        self._get = _load_xinput()
        self.available = self._get is not None
        self._binds = {}
        self._recording = False
        self._rec_union = set()
        self._connected = set()
        self._stop = threading.Event()
        self._thread = None

    @property
    def connected(self):
        return len(self._connected)

    def start(self):
        if not self.available:
            return False
        for i in range(4):          # 先同步扫一遍，界面一打开就知道有没有插手柄
            if self._read(i) is not None:
                self._connected.add(i)
        self._thread = threading.Thread(target=self._run, daemon=True, name="bbsl-pad")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(1)

    def set_binds(self, binds):
        table = {}
        for action, spec in binds.items():
            p = parse(spec)
            if p and len(p) >= 2:
                table[p] = action
        self._binds = table

    def record(self, on):
        self._rec_union = set()
        self._recording = on

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def _read(self, i):
        st = XINPUT_STATE()
        if self._get(i, ctypes.byref(st)) != 0:
            return None
        g = st.Gamepad
        held = {name for name, bit in BUTTONS if g.wButtons & bit}
        if g.bLeftTrigger > TRIGGER:
            held.add("pad_lt")
        if g.bRightTrigger > TRIGGER:
            held.add("pad_rt")
        return frozenset(held)

    def _run(self):
        since = {}          # 手柄号 -> (当前这组键, 开始按住的时间, 是否已经触发过)
        last_scan = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_scan >= RESCAN:
                last_scan = now
                slots = range(4)
            else:
                slots = list(self._connected)
            for i in slots:
                held = self._read(i)
                if held is None:
                    self._connected.discard(i)
                    since.pop(i, None)
                    continue
                self._connected.add(i)
                self._step(i, held, now, since)
            time.sleep(POLL)

    def _step(self, i, held, now, since):
        if self._recording:
            # 录制：把按下过的键都攒起来，全部松开时这一组就是录到的组合
            if held:
                self._rec_union |= held
            elif self._rec_union:
                combo, self._rec_union = self._rec_union, set()
                self._recording = False
                if len(combo) < 2:
                    self.events.put(("rec_bad", "至少要两个键的组合"))
                else:
                    self.events.put(("rec", build(combo)))
            since.pop(i, None)
            return

        prev = since.get(i)
        if prev is None or prev[0] != held:
            since[i] = (held, now, False)
            return
        combo, t0, fired = prev
        if not fired and combo in self._binds and now - t0 >= HOLD:
            since[i] = (combo, t0, True)
            self.events.put(("fire", self._binds[combo]))
