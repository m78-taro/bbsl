"""键鼠全局热键：用低级键盘钩子 + 低级鼠标钩子。

为什么不用 RegisterHotKey：它是独占的，绑了 Num1 之后游戏里就再也按不出 Num1。
钩子可以只在"整个组合都对上"的那一下把按键吃掉，其余情况原样放行：
  - 只按侧键 -> 游戏照常收到
  - 只按 Shift -> 游戏照常收到
  - Shift 按住再按侧键 -> 这一下侧键被吃掉，触发备份

钩子回调跑在钩子线程里，Tk 不是线程安全的，所以这里只往队列里塞事件，界面那边定时来取。
回调要尽量快：Windows 等不及（默认几百毫秒）会直接跳过甚至摘掉钩子。

注意：游戏要是以管理员身份运行，而 bbsl 不是，切到游戏窗口后钩子收不到按键（Windows 的权限隔离）。
"""
import ctypes
import ctypes.wintypes as wt
import queue
import threading

import keyspec

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_QUIT = 0x0012
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_LBUTTONDOWN, WM_RBUTTONDOWN = 0x0201, 0x0204
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C

DOWN_KEY = {WM_KEYDOWN, WM_SYSKEYDOWN}
UP_KEY = {WM_KEYUP, WM_SYSKEYUP}


def held_mods():
    return {m for m, _, vk in keyspec.MODS if user32.GetAsyncKeyState(vk) & 0x8000}


class Hotkeys:
    """用法：
        hk = Hotkeys(); hk.start()
        hk.set_binds({"save": "shift+mouse4", "load": "shift+mouse5"})
        界面里定时调 hk.poll()，拿到 ("fire", "save") / ("rec", spec) / ("rec_cancel", None) / ("rec_bad", None)
    """

    def __init__(self):
        self.events = queue.Queue()
        self._binds = {}            # (mods, main) -> action
        self._recording = False
        self._cancel_only = False   # 录手柄时键盘只管 Esc 取消，别的键照常放行
        self._swallowed = set()     # 吃掉了按下的主键，抬起也得吃掉，不然游戏会收到一个没头没尾的"抬起"
        self._thread = None
        self._tid = 0
        self._hooks = []
        self.error = None
        # 回调对象必须一直有引用，被回收了钩子就会调到野指针上崩掉
        self._kb_proc = HOOKPROC(self._on_kb)
        self._ms_proc = HOOKPROC(self._on_mouse)

    # ---------- 对外 ----------
    def start(self):
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True, name="bbsl-hooks")
        self._thread.start()
        ready.wait(2)
        return self.error is None

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(1)

    def set_binds(self, binds):
        """binds: {动作名: 规格串}。认不出来的规格直接忽略。"""
        table = {}
        for action, spec in binds.items():
            p = keyspec.parse(spec)
            if p:
                table[p] = action
        self._binds = table

    def record(self, on, cancel_only=False):
        """录制模式：下一次按下的键/鼠标键不触发动作，而是报给界面。
        cancel_only：只听 Esc（录手柄的时候用），其余按键放行，也不触发动作。"""
        self._cancel_only = cancel_only
        self._recording = on

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    # ---------- 钩子线程 ----------
    def _run(self, ready):
        self._tid = kernel32.GetCurrentThreadId()
        hmod = kernel32.GetModuleHandleW(None)
        for kind, proc in ((WH_KEYBOARD_LL, self._kb_proc), (WH_MOUSE_LL, self._ms_proc)):
            h = user32.SetWindowsHookExW(kind, proc, hmod, 0)
            if not h:
                self.error = f"装不上{'键盘' if kind == WH_KEYBOARD_LL else '鼠标'}钩子（错误 {ctypes.get_last_error()}）"
            else:
                self._hooks.append(h)
        ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        for h in self._hooks:
            user32.UnhookWindowsHookEx(h)
        self._hooks = []

    def _press(self, main, uid):
        """一个主键被按下。返回 True 表示这一下要吃掉。"""
        if uid in self._swallowed:
            return True              # 按住不放时的自动重复：已经处理过了，继续吃掉，也不再触发
        mods = held_mods()
        if self._recording and self._cancel_only:
            return False
        if self._recording:
            self._recording = False
            self._swallowed.add(uid)
            self.events.put(("rec", keyspec.build(mods, main)))
            return True
        action = self._binds.get((frozenset(mods), main))
        if action is None:
            return False
        self._swallowed.add(uid)
        self.events.put(("fire", action))
        return True

    def _release(self, uid):
        if uid in self._swallowed:
            self._swallowed.discard(uid)
            return True
        return False

    def _on_kb(self, code, wparam, lparam):
        if code == 0:
            k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = k.vkCode
            uid = ("k", vk)
            if wparam in DOWN_KEY and vk not in keyspec.MODIFIER_VKS:
                if self._recording and vk == keyspec.VK_ESCAPE:
                    self._recording = False
                    self._swallowed.add(uid)
                    self.events.put(("rec_cancel", None))
                    return 1
                if vk in keyspec.VK:
                    if self._press(keyspec.VK[vk][0], uid):
                        return 1
                elif self._recording and not self._cancel_only:
                    self._swallowed.add(uid)
                    self._recording = False
                    self.events.put(("rec_bad", None))
                    return 1
            elif wparam in UP_KEY and self._release(uid):
                return 1
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_mouse(self, code, wparam, lparam):
        if code == 0 and wparam in (WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP):
            m = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if wparam in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                main = "mouse3"
            else:
                main = "mouse4" if (m.mouseData >> 16) == 1 else "mouse5"
            uid = ("m", main)
            if wparam in (WM_MBUTTONDOWN, WM_XBUTTONDOWN):
                if self._press(main, uid):
                    return 1
            elif self._release(uid):
                return 1
        return user32.CallNextHookEx(None, code, wparam, lparam)
