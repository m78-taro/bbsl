"""程序内的弹窗：一层半透明遮罩盖住主窗口，中间放对话框。不用系统自带的 messagebox，风格对不上。"""
import tkinter as tk

from .theme import C, S, F
from .widgets import Button


class Modal:
    _current = None

    def __init__(self, root, title, width=380):
        if Modal._current:
            Modal._current.close()
        Modal._current = self
        self.root = root

        # 遮罩：Tk 的控件没法单独半透明，只能用一个无边框的半透明窗口盖上去
        self.scrim = tk.Toplevel(root)
        self.scrim.overrideredirect(True)
        self.scrim.configure(bg="#000000")
        self.scrim.attributes("-alpha", 0.55)
        self.scrim.bind("<Button-1>", lambda _e: self.close())

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=C["line"])
        card = tk.Frame(self.win, bg=C["panel"])
        card.pack(padx=1, pady=1, fill="both", expand=True)
        tk.Label(card, text=title, font=F(12, "bold"), bg=C["panel"], fg=C["text"], anchor="w") \
            .pack(fill="x", padx=S(22), pady=(S(18), S(8)))
        self.body = tk.Frame(card, bg=C["panel"])
        self.body.pack(fill="both", expand=True, padx=S(22))
        self.buttons = tk.Frame(card, bg=C["panel"])
        self.buttons.pack(fill="x", padx=S(22), pady=(S(18), S(18)))
        self.width = S(width)

        self.win.bind("<Escape>", lambda _e: self.close())
        self._follow = root.bind("<Configure>", lambda _e: self._place(), add="+")
        self.win.after_idle(self._show)

    def _show(self):
        self._place()
        self.win.lift()
        self.win.grab_set()
        self.win.focus_force()

    def _place(self):
        r = self.root
        x, y, w, h = r.winfo_rootx(), r.winfo_rooty(), r.winfo_width(), r.winfo_height()
        self.scrim.geometry(f"{w}x{h}+{x}+{y}")
        self.win.update_idletasks()
        dh = self.win.winfo_reqheight()
        self.win.geometry(f"{self.width}x{dh}+{x + (w - self.width) // 2}+{y + (h - dh) // 2 - S(20)}")
        self.scrim.lift()
        self.win.lift()

    def add_button(self, text, command, kind="default"):
        b = Button(self.buttons, text=text, kind=kind, command=command)
        b.pack(side="right", padx=(S(8), 0))
        return b

    def close(self):
        if Modal._current is self:
            Modal._current = None
        try:
            self.root.unbind("<Configure>", self._follow)
        except Exception:
            pass
        for w in (self.win, self.scrim):
            try:
                w.destroy()
            except Exception:
                pass


def confirm(root, title, message, ok_text="确定", on_ok=None, danger=False, detail=None):
    m = Modal(root, title)
    tk.Label(m.body, text=message, font=F(10), bg=C["panel"], fg=C["text"], justify="left",
             anchor="w", wraplength=m.width - S(44)).pack(fill="x")
    if detail:
        tk.Label(m.body, text=detail, font=F(9), bg=C["panel"], fg=C["dim"], justify="left",
                 anchor="w", wraplength=m.width - S(44)).pack(fill="x", pady=(S(8), 0))

    def ok():
        m.close()
        if on_ok:
            on_ok()

    m.add_button(ok_text, ok, kind="danger" if danger else "accent")
    m.add_button("取消", m.close)
    m.win.bind("<Return>", lambda _e: ok())
    return m

