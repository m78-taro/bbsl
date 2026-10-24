"""配色、字体和 DPI 缩放。

配色沿用 Stmsl，两个工具放一起看是一家的。
"""
import ctypes
import tkinter.font as tkfont

C = {
    "bg": "#0c0d12",
    "panel": "#141621",
    "panel2": "#1b1e2c",
    "line": "#262a3b",
    "hover": "#222637",
    "text": "#e6e8f0",
    "dim": "#8b90a6",
    "faint": "#5d6274",
    "accent": "#e0913c",
    "ok": "#4ca97a",
    "warn": "#d9a441",
    "err": "#d96a5a",
    "blue": "#5b8dd9",
    "purple": "#a07fd4",
}

UI = "Microsoft YaHei UI"
MONO = "Consolas"
ICON = None  # Win11 用 Segoe Fluent Icons，Win10 用 Segoe MDL2 Assets，码位相同

# Segoe 图标字体码位
I = {
    "folder": "\uE838",
    "refresh": "\uE72C",
    "save": "\uE74E",
    "restore": "\uE7A7",
    "delete": "\uE74D",
    "edit": "\uE70F",
    "key": "\uE765",
    "pad": "\uE7FC",
    "bell": "\uEA8F",
    "stack": "\uF156",
    "warn": "\uE7BA",
    "check": "\uE73E",
    "lock": "\uE72E",
    "unlock": "\uE785",
}

_scale = 1.0


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def init(root):
    """Tk 的字号按磅算会自己跟着 DPI 走，但像素尺寸不会，这里算出倍率给 S() 用。"""
    global _scale, ICON
    _scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
    fams = set(tkfont.families(root))
    for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if f in fams:
            ICON = f
            break


def S(px):
    return int(round(px * _scale))


def F(size=10, weight="normal", family=None):
    return (family or UI, size, weight)


def mix(fg, bg, t):
    """fg 和 bg 按比例混色，t=1 是纯 fg。用来做按钮底色这种"带一点颜色"的效果。"""
    a = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02x}" for x, y in zip(a, b))


def hwnd_of(root):
    root.update_idletasks()
    return ctypes.windll.user32.GetParent(root.winfo_id())




def custom_frame(root):
    """去掉系统标题栏和可拉伸的边框，最小化/关闭由顶栏自己画。窗口大小固定，不能最大化。

    没用 Tk 的 overrideredirect：那样任务栏里不显示，也不能从任务栏最小化/还原。
    这里只改窗口样式，保留 WS_MINIMIZEBOX 和 WS_SYSMENU，任务栏的行为都还在。
    Win11 上再让系统把四个角画成圆角，外框画成一条细线。
    """
    try:
        u = ctypes.windll.user32
        hwnd = hwnd_of(root)
        u.GetWindowLongW.restype = ctypes.c_long
        style = u.GetWindowLongW(hwnd, -16)                      # GWL_STYLE
        # 去掉 WS_CAPTION、WS_THICKFRAME（拉伸边框）、WS_MAXIMIZEBOX
        u.SetWindowLongW(hwnd, -16, style & ~0x00C00000 & ~0x00040000 & ~0x00010000)
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)               # 不动位置大小，只让边框重新计算

        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute

        def setattr_(attr, value):
            v = ctypes.c_int(value)
            dwm(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        r, g, b = int(C["line"][1:3], 16), int(C["line"][3:5], 16), int(C["line"][5:7], 16)
        setattr_(20, 1)                          # 深色模式
        setattr_(33, 2)                          # DWMWA_WINDOW_CORNER_PREFERENCE = 圆角（Win11）
        setattr_(34, (b << 16) | (g << 8) | r)   # 外框颜色（Win11）
        return hwnd
    except Exception:
        return None


class Dragger:
    """按住顶栏拖动窗口。

    自己算位置挪窗口，不走系统的拖动（WM_NCLBUTTONDOWN）：
    系统拖动会进入它自己的消息循环，和 Tk 的事件循环、bbsl 的全局鼠标钩子搅在一起会卡住甚至崩溃。
    """

    def __init__(self, root):
        self.root = root
        self.dx = self.dy = None

    def bind(self, *widgets):
        for w in widgets:
            w.bind("<ButtonPress-1>", self._press, add="+")
            w.bind("<B1-Motion>", self._move, add="+")
            w.bind("<ButtonRelease-1>", self._release, add="+")

    def _press(self, e):
        self.dx = e.x_root - self.root.winfo_x()
        self.dy = e.y_root - self.root.winfo_y()

    def _move(self, e):
        if self.dx is not None:
            self.root.geometry(f"+{e.x_root - self.dx}+{e.y_root - self.dy}")

    def _release(self, e):
        self._move(e)          # 松手的位置也算上，快速拖的时候最后几下移动事件可能被合并掉
        self.dx = self.dy = None
