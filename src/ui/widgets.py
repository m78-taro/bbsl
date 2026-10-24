"""自绘的扁平控件。Tk 自带的按钮在 Windows 上改不了边框和悬停色，所以都用 Label/Canvas 拼。"""
import tkinter as tk
from tkinter import ttk

from . import theme
from .theme import C, S, F, I, mix


def bind_tree(widget, seq, fn):
    """事件绑到控件和它所有子控件上。否则鼠标移到按钮里的文字上，悬停效果就断了。"""
    widget.bind(seq, fn, add="+")
    for ch in widget.winfo_children():
        bind_tree(ch, seq, fn)


def inside(widget, event):
    x, y = event.x_root, event.y_root
    wx, wy = widget.winfo_rootx(), widget.winfo_rooty()
    return wx <= x < wx + widget.winfo_width() and wy <= y < wy + widget.winfo_height()


class Button(tk.Frame):
    """kind: default / blue / accent / danger / ghost"""

    def __init__(self, parent, text="", icon=None, kind="default", command=None,
                 sub=None, big=False, disabled=False):
        super().__init__(parent, highlightthickness=1, cursor="hand2")
        self.kind, self.command, self.disabled = kind, command, disabled
        self.hovering = False
        pad_x, pad_y = (S(18), S(12)) if big else (S(12), S(5))
        inner = tk.Frame(self)
        inner.pack(padx=pad_x, pady=pad_y, fill="both", expand=True)
        self.inner = inner
        self.icon_lbl = None
        if icon and theme.ICON:
            self.icon_lbl = tk.Label(inner, text=I[icon], font=(theme.ICON, 15 if big else 10))
            self.icon_lbl.pack(side="left", padx=(0, S(10) if big else S(6)) if text else 0)
        col = tk.Frame(inner)
        col.pack(side="left", fill="both", expand=True)
        self.col = col
        self.text_lbl = tk.Label(col, text=text, font=F(13 if big else 10, "bold" if big else "normal"),
                                 anchor="w")
        self.text_lbl.pack(anchor="w")
        self.sub_lbl = None
        if sub is not None:
            self.sub_lbl = tk.Label(col, text=sub, font=F(9), anchor="w")
            self.sub_lbl.pack(anchor="w")
        bind_tree(self, "<Enter>", self._enter)
        bind_tree(self, "<Leave>", self._leave)
        bind_tree(self, "<ButtonRelease-1>", self._click)
        self._paint()

    def _palette(self):
        """返回 (底色, 边框, 文字, 副文字)。"""
        k = self.kind
        if self.disabled:
            if k == "ghost":
                bg = self.master.cget("bg")
                return bg, bg, C["faint"], C["faint"]
            return C["panel2"], C["line"], C["faint"], C["faint"]
        if k in ("blue", "accent"):
            col = C[k]
            bg = mix(col, C["panel"], 0.26 if self.hovering else 0.15)
            return bg, col, C["text"], mix(col, C["text"], 0.5)
        if k == "danger":
            if self.hovering:
                return C["panel2"], C["err"], C["err"], C["err"]
            return C["panel2"], C["line"], C["text"], C["dim"]
        if k == "ghost":
            bg = self.master.cget("bg")
            return bg, bg, C["text"] if self.hovering else C["dim"], C["faint"]
        if self.hovering:
            return C["hover"], C["dim"], C["text"], C["dim"]
        return C["panel2"], C["line"], C["text"], C["dim"]

    def _paint(self):
        bg, border, fg, sub = self._palette()
        self.configure(bg=bg, highlightbackground=border, highlightcolor=border,
                       cursor="arrow" if self.disabled else "hand2")
        for w in (self.inner, self.col):
            w.configure(bg=bg)
        self.text_lbl.configure(bg=bg, fg=fg)
        if self.icon_lbl:
            colored = self.kind in ("blue", "accent") and not self.disabled
            self.icon_lbl.configure(bg=bg, fg=C[self.kind] if colored else fg)
        if self.sub_lbl:
            self.sub_lbl.configure(bg=bg, fg=sub)

    def _enter(self, _e):
        if not self.hovering:
            self.hovering = True
            self._paint()

    def _leave(self, e):
        if not inside(self, e):
            self.hovering = False
            self._paint()

    def _click(self, e):
        if not self.disabled and self.command and inside(self, e):
            self.command()

    def set_disabled(self, v):
        self.disabled = v
        self._paint()

    def set_sub(self, text):
        if self.sub_lbl:
            self.sub_lbl.configure(text=text)


class Toggle(tk.Canvas):
    def __init__(self, parent, value=False, command=None, color=None):
        self.w, self.h = S(36), S(20)
        super().__init__(parent, width=self.w, height=self.h, highlightthickness=0,
                         bg=parent.cget("bg"), cursor="hand2")
        self.value, self.command, self.color = value, command, color or C["blue"]
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _pill(self, x0, y0, x1, y1, fill):
        r = (y1 - y0) / 2
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=fill, outline=fill)
        self.create_oval(x1 - 2 * r, y0, x1, y1, fill=fill, outline=fill)
        self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline=fill)

    def _draw(self):
        self.delete("all")
        w, h = self.w, self.h
        self._pill(1, 1, w - 1, h - 1, self.color if self.value else C["line"])
        d = h - S(8)
        x = w - S(4) - d if self.value else S(4)
        self.create_oval(x, S(4), x + d, S(4) + d, fill=C["text"] if self.value else C["dim"], outline="")

    def _toggle(self, _e=None):
        self.value = not self.value
        self._draw()
        if self.command:
            self.command(self.value)


class Seg(tk.Frame):
    """分段选择。"""

    def __init__(self, parent, options, value, command=None, color=None):
        super().__init__(parent, bg=C["line"])
        self.color, self.command, self.value = color or C["blue"], command, value
        self.items = {}
        self._dim = set()       # 显示成灰色（暂时不能选）的那几段
        for i, (val, label) in enumerate(options):
            lbl = tk.Label(self, text=label, font=F(9), padx=S(10), pady=S(4), cursor="hand2")
            lbl.grid(row=0, column=i, padx=(1, 1 if i == len(options) - 1 else 0), pady=1, sticky="nsew")
            self.columnconfigure(i, weight=1, uniform="seg")   # 每段一样宽，不按字数多少
            lbl.bind("<Button-1>", lambda _e, v=val: self.set(v, fire=True))
            self.items[val] = lbl
        self._paint()

    def _paint(self):
        for val, lbl in self.items.items():
            on = val == self.value
            lbl.configure(bg=mix(self.color, C["panel"], 0.28) if on else C["panel2"],
                          fg=C["text"] if on else (C["faint"] if val in self._dim else C["dim"]),
                          cursor="arrow" if val in self._dim else "hand2")

    def set_dim(self, v, dim):
        (self._dim.add if dim else self._dim.discard)(v)
        self._paint()

    def set(self, v, fire=False):
        self.value = v
        self._paint()
        if fire and self.command:
            self.command(v)


class Stepper(tk.Frame):
    """[−] 数字 [+]"""

    def __init__(self, parent, value, lo, hi, step=1, command=None, unit=""):
        super().__init__(parent, bg=C["line"])
        self.value, self.lo, self.hi, self.step, self.command, self.unit = value, lo, hi, step, command, unit

        def mk(t):
            return tk.Label(self, text=t, font=F(10), bg=C["panel2"], fg=C["dim"],
                            width=2, cursor="hand2", pady=S(2))

        self.minus, self.plus = mk("−"), mk("+")
        self.lbl = tk.Label(self, font=F(10), bg=C["panel2"], fg=C["text"], width=6)
        self.minus.grid(row=0, column=0, padx=(1, 0), pady=1)
        self.lbl.grid(row=0, column=1, padx=1, pady=1, sticky="ns")
        self.plus.grid(row=0, column=2, padx=(0, 1), pady=1)
        self.minus.bind("<Button-1>", lambda _e: self.bump(-1))
        self.plus.bind("<Button-1>", lambda _e: self.bump(1))
        for b in (self.minus, self.plus):
            b.bind("<Enter>", lambda e: e.widget.configure(fg=C["text"]))
            b.bind("<Leave>", lambda e: e.widget.configure(fg=C["dim"]))
        self._paint()

    def _paint(self):
        self.lbl.configure(text=f"{self.value}{self.unit}")

    def bump(self, d):
        v = min(self.hi, max(self.lo, self.value + d * self.step))
        if v != self.value:
            self.value = v
            self._paint()
            if self.command:
                self.command(v)


class KeyField(tk.Label):
    """显示一个热键，点一下进入录制。录制逻辑在 App 里，这里只管样子。"""

    def __init__(self, parent, text, command=None):
        # 不用等宽字体：要显示"下侧键"这种中文，Consolas 没有中文字形
        super().__init__(parent, text=text, font=F(9), bg=C["panel2"], fg=C["text"],
                         padx=S(8), pady=S(4), width=1, highlightthickness=1,
                         highlightbackground=C["line"], cursor="hand2")
        self.command = command
        self.state = "idle"
        self.bind("<Button-1>", lambda _e: command and command())
        self.bind("<Enter>", lambda _e: self.state == "idle" and self.configure(highlightbackground=C["dim"]))
        self.bind("<Leave>", lambda _e: self.state == "idle" and self.configure(highlightbackground=C["line"]))

    def show(self, text, state="idle"):
        self.state = state
        col = {"idle": None, "rec": C["accent"], "err": C["err"]}[state]
        self.configure(text=text, highlightbackground=col or C["line"], highlightcolor=col or C["line"],
                       fg=col or C["text"])


class ScrollArea(tk.Frame):
    """可滚动的竖向容器，内容放进 .body。"""

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                 style="Dark.Vertical.TScrollbar")
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind_all("<MouseWheel>", self._wheel, add="+")

    def _on_scroll(self, lo, hi):
        # 内容放得下就把滚动条藏起来
        if float(lo) <= 0 and float(hi) >= 1:
            self.bar.pack_forget()
        else:
            self.bar.pack(side="right", fill="y")
        self.bar.set(lo, hi)

    def _wheel(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        while w is not None and w is not self:
            w = w.master
        if w is self:
            self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def to_top(self):
        self.canvas.yview_moveto(0)


def style_ttk(root):
    st = ttk.Style(root)
    st.theme_use("clam")
    st.layout("Dark.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
        "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})], "sticky": "ns"})])
    st.configure("Dark.Vertical.TScrollbar", background=C["line"], troughcolor=C["bg"],
                 bordercolor=C["bg"], lightcolor=C["line"], darkcolor=C["line"], width=S(8))
    st.map("Dark.Vertical.TScrollbar", background=[("active", C["faint"])])
