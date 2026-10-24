"""游戏里按了热键之后的提示浮窗。

游戏全屏的时候看不到主窗口，按了不知道成没成，所以在屏幕上方弹一个小条，一两秒后淡出。
它不能抢焦点（否则游戏会被切到后台），鼠标也要能穿过去。
注意：游戏要是"独占全屏"，任何窗口都盖不上去，只有"无边框窗口"模式能看到它。
"""
import ctypes
import tkinter as tk

from .theme import C, S, F, I
from . import theme

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020   # 鼠标穿透
WS_EX_TOOLWINDOW = 0x00000080    # 不进任务栏、不进 Alt+Tab
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000    # 不抢焦点

_current = None


def _no_activate(win):
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        u = ctypes.windll.user32
        style = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TOPMOST | WS_EX_TRANSPARENT
                         | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE)
    except Exception:
        pass


def show(root, text, sub=None, kind="ok", ms=1600):
    """kind: ok / load / err"""
    global _current
    if _current is not None:
        try:
            _current.destroy()
        except Exception:
            pass

    color = {"ok": C["blue"], "load": C["accent"], "err": C["err"]}[kind]
    icon = {"ok": "save", "load": "restore", "err": "warn"}[kind]

    win = tk.Toplevel(root)
    _current = win
    win.withdraw()
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg=color)

    card = tk.Frame(win, bg=C["panel"])
    card.pack(padx=(S(4), 1), pady=1)   # 左边留 4px 露出底色，就是一条彩色竖条
    row = tk.Frame(card, bg=C["panel"])
    row.pack(padx=S(16), pady=S(10))
    if theme.ICON:
        tk.Label(row, text=I[icon], font=(theme.ICON, 14), bg=C["panel"], fg=color) \
            .pack(side="left", padx=(0, S(12)))
    col = tk.Frame(row, bg=C["panel"])
    col.pack(side="left")
    tk.Label(col, text=text, font=F(11, "bold"), bg=C["panel"], fg=C["text"], anchor="w").pack(anchor="w")
    if sub:
        tk.Label(col, text=sub, font=F(9), bg=C["panel"], fg=C["dim"], anchor="w").pack(anchor="w")

    win.update_idletasks()
    w = win.winfo_reqwidth()
    sw = win.winfo_screenwidth()
    win.geometry(f"+{(sw - w) // 2}+{S(48)}")
    win.attributes("-alpha", 0.95)
    win.deiconify()
    _no_activate(win)

    def fade(a=0.95):
        if _current is not win:
            return
        a -= 0.08
        if a <= 0:
            win.destroy()
            return
        win.attributes("-alpha", a)
        win.after(30, fade, a)

    win.after(ms, fade)
