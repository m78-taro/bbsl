"""主窗口。"""
import datetime as dt
import os
import tkinter as tk
import tkinter.font as tkfont

import keyspec as keys
from backend.stub import MAX_LOCKED, MIN_KEEP

from . import dialogs, sound, theme, toast
from .theme import C, S, F, I, mix
from .widgets import Button, KeyField, ScrollArea, Seg, Stepper, Toggle, bind_tree, inside, style_ttk

VERSION = "v0.1"
CREDIT = ("@丙👾", "Claude")


def rel_time(t):
    if t is None:
        return "—"
    d = dt.datetime.now() - t
    s = int(d.total_seconds())
    if s < 60:
        return "刚刚"
    if s < 3600:
        return f"{s // 60} 分钟前"
    if s < 86400:
        return f"{s // 3600} 小时前"
    return f"{d.days} 天前"


def short_time(t):
    today = dt.date.today()
    if t.date() == today:
        return "今天 " + t.strftime("%H:%M:%S")
    if t.date() == today - dt.timedelta(days=1):
        return "昨天 " + t.strftime("%H:%M:%S")
    return t.strftime("%m-%d %H:%M")


def elide_middle(text, font, max_px):
    """放不下就把中间换成"…"，两头留着：路径的盘符和末尾的 SPRJ0005 都是有用的信息。"""
    if max_px <= 0 or font.measure(text) <= max_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        k = (lo + hi + 1) // 2
        head, tail = text[:k - k // 2], text[len(text) - k // 2:]
        if font.measure(head + "…" + tail) <= max_px:
            lo = k
        else:
            hi = k - 1
    return text[:lo - lo // 2] + "…" + text[len(text) - lo // 2:]


def human_size(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


class GradientText(tk.Canvas):
    """署名：逐字插值上色，模拟 Stmsl 那条从橙到紫的渐变字。"""

    def __init__(self, parent, parts, bg):
        f = tkfont.Font(family=theme.UI, size=11, weight="bold")
        sep = tkfont.Font(family=theme.UI, size=11)
        a, b = parts
        sep_txt = "  |  "
        w = f.measure(a) + sep.measure(sep_txt) + f.measure(b)
        h = f.metrics("linespace")
        super().__init__(parent, width=w + 2, height=h, bg=bg, highlightthickness=0)
        stops = [C["accent"], "#e8b45c", C["purple"]]

        def color(t):
            if t < 0.4:
                return mix(stops[1], stops[0], t / 0.4)
            return mix(stops[2], stops[1], (t - 0.4) / 0.6)

        x = 1
        total = w
        for part_i, text in enumerate((a, b)):
            for ch in text:
                cw = f.measure(ch)
                self.create_text(x, h // 2, text=ch, font=f, fill=color((x + cw / 2) / total), anchor="w")
                x += cw
            if part_i == 0:
                self.create_text(x, h // 2, text=sep_txt, font=sep, fill=C["faint"], anchor="w")
                x += sep.measure(sep_txt)


class App:
    def __init__(self, root, backend, hotkeys=None, hotkeys_error=None, pad=None):
        self.root, self.be = root, backend
        self.hk, self.hk_error = hotkeys, hotkeys_error
        self.pad = pad
        self._pad_seen = None
        self.cfg = backend.get_config()
        self._mode = self._wanted_mode()   # 当前生效的热键：km / pad
        self.info = None
        self.recording = None          # 正在录制哪个键（save_key / load_key）
        self._rec_timer = None
        self._flash_timer = None

        root.title("bbsl")
        root.configure(bg=C["bg"])
        w, h = S(1040), S(700)
        self._geom = f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}"
        root.geometry(self._geom)
        root.resizable(False, False)   # 窗口大小固定
        style_ttk(root)

        self._build_header()
        tk.Frame(root, bg=C["line"], height=1).pack(fill="x")
        body = tk.Frame(root, bg=C["bg"])
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.main = tk.Frame(body, bg=C["bg"])
        self.main.grid(row=0, column=0, sticky="nsew")
        tk.Frame(body, bg=C["line"], width=1).grid(row=0, column=1, sticky="ns")
        side = tk.Frame(body, bg=C["panel"], width=S(330))
        side.grid(row=0, column=2, sticky="ns")
        side.grid_propagate(False)
        side.pack_propagate(False)
        self._build_side(side)
        self._build_main()

        self.refresh_all()
        self._apply_binds()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(30, self._poll_hotkeys)
        theme.custom_frame(root)
        # 去掉标题栏后系统保留了原来的外框尺寸，内容区会被撑大一圈，这里按设计尺寸重新设一次
        root.geometry(self._geom)
        if self.hk is None:
            self.flash("热键没装上：" + (self.hk_error or "未知原因"), "err")

    # ================= 顶栏 =================
    def _build_header(self):
        """顶栏兼标题栏：左边名字，中间署名，右边存档状态和窗口按钮。空白处按住可以拖动窗口。"""
        bar = tk.Frame(self.root, bg=C["panel"], height=S(48))
        bar.pack(fill="x")
        bar.pack_propagate(False)

        # 窗口按钮：贴着右上角，撑满顶栏高度，和系统的一样
        self.win_btns = {}
        for name, glyph in (("close", "\uE8BB"), ("min", "\uE921")):
            b = tk.Label(bar, text=glyph, font=(theme.ICON or theme.UI, 9), width=5,
                         bg=C["panel"], fg=C["dim"], cursor="arrow")
            b.pack(side="right", fill="y")
            hover_bg, hover_fg = ("#c42b1c", "#ffffff") if name == "close" else (C["hover"], C["text"])
            b.bind("<Enter>", lambda _e, w=b, bg=hover_bg, fg=hover_fg: w.configure(bg=bg, fg=fg))
            b.bind("<Leave>", lambda _e, w=b: w.configure(bg=C["panel"], fg=C["dim"]))
            self.win_btns[name] = b
        self.win_btns["close"].bind("<ButtonRelease-1>", lambda _e: self._close())
        self.win_btns["min"].bind("<ButtonRelease-1>", lambda _e: self.root.iconify())

        left = tk.Frame(bar, bg=C["panel"])
        left.pack(side="left", padx=S(20))
        name = tk.Label(left, text="bbsl", font=F(13, "bold"), bg=C["panel"], fg=C["text"])
        name.pack(side="left")
        sub = tk.Label(left, text="血源诅咒 · 快捷 S/L", font=F(9), bg=C["panel"], fg=C["dim"])
        sub.pack(side="left", padx=(S(10), 0), pady=(S(3), 0))

        self.pill = tk.Frame(bar, bg=C["panel2"], highlightthickness=1, highlightbackground=C["line"])
        self.pill.pack(side="right", padx=(0, S(16)))
        self.pill_dot = tk.Label(self.pill, text="●", font=F(9), bg=C["panel2"])
        self.pill_dot.pack(side="left", padx=(S(10), S(4)), pady=S(2))
        self.pill_txt = tk.Label(self.pill, font=F(9), bg=C["panel2"], fg=C["text"])
        self.pill_txt.pack(side="left", padx=(0, S(12)))

        credit = GradientText(bar, CREDIT, C["panel"])
        credit.place(relx=0.5, rely=0.5, anchor="center")

        # 能拖窗口的地方：顶栏空白、名字、署名、状态标签
        self._dragger = theme.Dragger(self.root)
        self._dragger.bind(bar, left, name, sub, credit, self.pill, self.pill_dot, self.pill_txt)

    # ================= 左侧主区域 =================
    def _build_main(self):
        m = tk.Frame(self.main, bg=C["bg"])
        m.pack(fill="both", expand=True, padx=S(24), pady=(S(20), S(0)))

        # 卡片不加边框，靠底色和背景区分：里面的按钮已经有边框了，边框套边框显得乱
        self.card = tk.Frame(m, bg=C["panel"])
        self.card.pack(fill="x")

        actions = tk.Frame(m, bg=C["bg"])
        actions.pack(fill="x", pady=(S(16), 0))
        actions.columnconfigure(0, weight=1, uniform="a")
        actions.columnconfigure(1, weight=1, uniform="a")
        self.btn_save = Button(actions, "备份", icon="save", kind="blue", big=True, sub="", command=self.do_save)
        self.btn_save.grid(row=0, column=0, sticky="nsew", padx=(0, S(8)))
        self.btn_load = Button(actions, "还原最新", icon="restore", kind="accent", big=True, sub="",
                               command=lambda: self.do_load(None))
        self.btn_load.grid(row=0, column=1, sticky="nsew", padx=(S(8), 0))

        # 使用方法。还原必须在游戏外（标题画面或者关掉游戏都行）：
        # 在游戏里直接还原，下一次自动存档会把它盖掉
        tip = tk.Frame(m, bg=C["bg"])
        tip.pack(fill="x", pady=(S(12), 0))
        usage = [
            ("备份方法", [("退回标题画面 / 退出游戏", None), ("按备份", C["blue"])]),
            ("还原方法", [("退回标题画面 / 退出游戏", None), ("按还原", C["accent"]), ("继续游戏", None)]),
        ]
        for r, (title, steps) in enumerate(usage):
            tk.Label(tip, text=title, font=F(9), bg=C["bg"], fg=C["faint"]) \
                .grid(row=r, column=0, sticky="w", padx=(0, S(12)), pady=S(3))
            line = tk.Frame(tip, bg=C["bg"])
            line.grid(row=r, column=1, sticky="w")
            for i, (text, col) in enumerate(steps):
                if i:
                    tk.Label(line, text="→", font=F(9), bg=C["bg"], fg=C["faint"]).pack(side="left", padx=S(6))
                tk.Label(line, text=text, font=F(9), padx=S(8), pady=S(1),
                         bg=mix(col, C["bg"], 0.16) if col else C["panel2"], fg=col or C["dim"],
                         highlightthickness=1, highlightbackground=col or C["line"]).pack(side="left")

        head = tk.Frame(m, bg=C["bg"])
        head.pack(fill="x", pady=(S(22), S(8)))
        tk.Label(head, text="快照", font=F(12, "bold"), bg=C["bg"], fg=C["text"]).pack(side="left")
        self.count_lbl = tk.Label(head, font=F(10), bg=C["bg"], fg=C["faint"])
        self.count_lbl.pack(side="left", padx=(S(8), 0), pady=(S(2), 0))
        Button(head, "打开快照目录", icon="folder", kind="ghost",
               command=lambda: self._open(self.be.snapshot_dir())).pack(side="right")
        tk.Label(head, text="双击名字可以改名", font=F(9), bg=C["bg"], fg=C["faint"]) \
            .pack(side="right", padx=(0, S(10)))

        frame = tk.Frame(m, bg=C["line"])
        frame.pack(fill="both", expand=True)
        self.list = ScrollArea(frame, C["bg"])
        self.list.pack(fill="both", expand=True, padx=1, pady=1)

        self.status = tk.Label(m, font=F(9), bg=C["bg"], fg=C["faint"], anchor="w")
        self.status.pack(fill="x", pady=(S(8), S(10)))

    def _render_card(self):
        for w in self.card.winfo_children():
            w.destroy()
        info = self.info
        inner = tk.Frame(self.card, bg=C["panel"])
        inner.pack(fill="x", padx=S(20), pady=S(16))

        if not info.found:
            top = tk.Frame(inner, bg=C["panel"])
            top.pack(fill="x")
            if theme.ICON:
                tk.Label(top, text=I["warn"], font=(theme.ICON, 16), bg=C["panel"], fg=C["err"]) \
                    .pack(side="left", padx=(0, S(12)))
            tk.Label(top, text="没找到存档", font=F(12, "bold"), bg=C["panel"], fg=C["text"]) \
                .pack(side="left")
            Button(top, "重新检测", icon="refresh", command=self.redetect).pack(side="right")
            # Tk 只在空格处换行，一长串中文会被当成一个词，所以这里手动断成两句
            msg = tk.Label(inner, text="把 bbsl 放进游戏目录（和 Bloodborne.exe 同一层），或者游戏目录下的任意文件夹里。\n"
                                       "它会自己往上找 user\\savedata 里的存档。",
                           font=F(10), bg=C["panel"], fg=C["dim"], justify="left", anchor="w")
            msg.pack(fill="x", pady=(S(10), 0))
            msg.bind("<Configure>", lambda e: msg.configure(wraplength=e.width))
            row = tk.Frame(inner, bg=C["panel"])
            row.pack(fill="x", pady=(S(8), 0))
            tk.Label(row, text="从这里开始找的：", font=F(9), bg=C["panel"], fg=C["faint"]).pack(side="left")
            tk.Label(row, text=info.search_from, font=F(9), bg=C["panel"], fg=C["faint"]).pack(side="left")
            return

        def line(label, value, extra=None, elide=False, buttons=()):
            r = tk.Frame(inner, bg=C["panel"])
            r.pack(fill="x", pady=S(3))
            tk.Label(r, text=label, font=F(9), bg=C["panel"], fg=C["faint"], width=8, anchor="w").pack(side="left")
            for b in reversed(buttons):
                b(r).pack(side="right", padx=(S(6), 0))
            # 路径不用等宽字体：Consolas 没有中文，"血源诅咒"会退回宋体，很难看
            v = tk.Label(r, text=value, font=F(10), bg=C["panel"], fg=C["text"], anchor="w")
            v.pack(side="left", fill="x", expand=elide)
            if elide:
                fnt = tkfont.Font(font=v.cget("font"))
                v.bind("<Configure>", lambda e: v.configure(text=elide_middle(value, fnt, e.width - S(12))))
            if extra:
                tk.Label(r, text=extra, font=F(9), bg=C["panel"], fg=C["dim"]).pack(side="left", padx=(S(10), 0))
            return r

        line("存档目录", info.save_dir, elide=True, buttons=(
            lambda p: Button(p, "打开", icon="folder", command=lambda: self._open(info.save_dir)),
            lambda p: Button(p, "重新检测", icon="refresh", command=self.redetect),
        ))
        chars = "、".join(n for _, n in info.characters) or "（空）"
        slots = "、".join(str(s) for s, _ in info.characters)
        line("角色", chars, extra=f"槽位 {slots}" if slots else None)
        line("最后写入", info.mtime.strftime("%Y-%m-%d %H:%M:%S") if info.mtime else "—",
             extra=rel_time(info.mtime))

    def _render_list(self):
        body = self.list.body
        # 记住滚到哪儿了：在列表下面删了一个快照，不该一下子跳回顶上
        keep = self.list.canvas.yview()[0]
        for w in body.winfo_children():
            w.destroy()
        snaps = self.be.snapshots()
        # 锁住的置顶，两组里面都是新的在上。只影响显示，还原热键还是还原时间最新的那份
        snaps = [s for s in snaps if s.locked] + [s for s in snaps if not s.locked]
        locked = sum(1 for s in snaps if s.locked)
        self.count_lbl.configure(text=f"{len(snaps)} 个　·　已锁 {locked}/{MAX_LOCKED}")
        if not snaps:
            tk.Label(body, text="还没有快照。在游戏里按一下备份热键，或者点上面的「备份」。",
                     font=F(10), bg=C["bg"], fg=C["faint"]).pack(pady=S(40))
            return
        for s in snaps:
            self._row(body, s)
        body.update_idletasks()
        self.list.canvas.configure(scrollregion=self.list.canvas.bbox("all"))
        self.list.canvas.yview_moveto(keep)

    def _row(self, parent, s):
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(fill="x")
        tk.Frame(parent, bg=C["line"], height=1).pack(fill="x")
        inner = tk.Frame(row, bg=C["bg"])
        inner.pack(fill="x", padx=S(16), pady=S(9))
        inner.columnconfigure(0, weight=1)

        name = tk.Label(inner, text=s.name, font=F(10, family=theme.MONO if s.auto_named else None),
                        bg=C["bg"], fg=C["dim"] if s.auto_named else C["text"], anchor="w", cursor="xterm")
        name.grid(row=0, column=0, sticky="w")
        name.bind("<Double-Button-1>", lambda _e: self.do_rename(s, name))

        # 锁：单击上锁/解锁。锁住的不会被自动删
        lock_fg = C["warn"] if s.locked else C["faint"]
        lock = tk.Label(inner, text=I["lock" if s.locked else "unlock"] if theme.ICON else ("锁" if s.locked else "—"),
                        font=(theme.ICON, 11) if theme.ICON else F(9), bg=C["bg"], fg=lock_fg,
                        width=3, cursor="hand2")
        lock.grid(row=0, column=1, padx=(S(10), S(10)))
        lock.bind("<Button-1>", lambda _e: self.do_lock(s))
        lock.bind("<Enter>", lambda _e: lock.configure(fg=C["warn"] if s.locked else C["dim"]))
        lock.bind("<Leave>", lambda _e: lock.configure(fg=lock_fg))

        tk.Label(inner, text=short_time(s.time), font=F(9), bg=C["bg"], fg=C["dim"], width=16, anchor="w") \
            .grid(row=0, column=2)
        tk.Label(inner, text=human_size(s.size), font=F(9), bg=C["bg"], fg=C["faint"], width=7, anchor="e") \
            .grid(row=0, column=3, padx=(0, S(16)))
        acts = tk.Frame(inner, bg=C["bg"])
        acts.grid(row=0, column=4)
        restore = Button(acts, "还原", kind="ghost", command=lambda: self.do_load(s, ask=True),
                         disabled=not self.info.found)
        restore.pack(side="left")
        Button(acts, "删除", kind="ghost", command=lambda: self.do_delete(s)).pack(side="left")

        # 行悬停高亮：整行连同子控件一起换底色（按钮除外，它们自己管）
        def paint(bg):
            stack = [row]
            while stack:
                w = stack.pop()
                if isinstance(w, Button):
                    w._paint()
                    continue
                if getattr(w, "_keep_bg", False):
                    continue          # 改名输入框有自己的底色和边框，别被行悬停刷掉
                w.configure(bg=bg)
                stack.extend(w.winfo_children())

        def enter(_e):
            paint(C["panel"])

        def leave(e):
            if not inside(row, e):
                paint(C["bg"])

        bind_tree(row, "<Enter>", enter)
        bind_tree(row, "<Leave>", leave)

    # ================= 右侧设置 =================
    def _build_side(self, side):
        area = ScrollArea(side, C["panel"])
        area.pack(fill="both", expand=True)
        p = area.body
        pad = S(22)

        def section(title, icon, toggle=None):
            f = tk.Frame(p, bg=C["panel"])
            f.pack(fill="x", padx=pad, pady=(S(18), S(2)))
            if theme.ICON:
                tk.Label(f, text=I[icon], font=(theme.ICON, 11), bg=C["panel"], fg=C["dim"]) \
                    .pack(side="left", padx=(0, S(8)))
            tk.Label(f, text=title, font=F(11, "bold"), bg=C["panel"], fg=C["text"]).pack(side="left")
            if toggle:
                toggle(f).pack(side="right")
            return f

        def row(label, make, parent=None):
            r = tk.Frame(parent or p, bg=C["panel"])
            r.pack(fill="x", padx=pad, pady=S(4))
            tk.Label(r, text=label, font=F(10), bg=C["panel"], fg=C["dim"]).pack(side="left")
            w = make(r)
            w.pack(side="right")
            return w

        def key_row(label, which, parent):
            r = tk.Frame(parent, bg=C["panel"])
            r.pack(fill="x", padx=pad, pady=(S(6), 0))
            r.columnconfigure(0, weight=1, uniform="half")
            r.columnconfigure(1, weight=1, uniform="half")
            tk.Label(r, text=label, font=F(10), bg=C["panel"], fg=C["dim"], anchor="w") \
                .grid(row=0, column=0, sticky="w")
            f = KeyField(r, "", lambda: self.start_record(which))
            f.grid(row=0, column=1, sticky="ew")
            return f

        def note(text, color=None, parent=None):
            lbl = tk.Label(parent or p, text=text, font=F(9), bg=C["panel"], fg=color or C["faint"],
                           justify="left", anchor="w", wraplength=S(330) - 2 * pad)
            lbl.pack(fill="x", padx=pad, pady=(S(4), 0))
            return lbl

        # ---- 热键：键鼠和手柄二选一，只有选中的那套生效 ----
        section("热键", "key")
        seg_row = tk.Frame(p, bg=C["panel"])
        seg_row.pack(fill="x", padx=pad, pady=(S(6), S(4)))
        self.input_seg = Seg(seg_row, [("km", "键鼠"), ("pad", "Xbox 手柄")], self._mode,
                             command=self._on_mode_click)
        self.input_seg.pack(fill="x")
        holder = tk.Frame(p, bg=C["panel"])
        holder.pack(fill="x")
        self.kf = {}

        km = tk.Frame(holder, bg=C["panel"])
        self.kf["save_key"] = key_row("备份", "save_key", km)
        self.kf["load_key"] = key_row("还原", "load_key", km)
        self.rec_hint = tk.Frame(km, bg=C["panel"])
        self.rec_hint.pack(fill="x", padx=pad, pady=(S(4), 0))
        self._hint_idle()
        note("只有整个组合按下才拦截。单按Shift、单按侧键，游戏照常收到。", parent=km)

        pd = tk.Frame(holder, bg=C["panel"])
        self.kf["pad_save"] = key_row("备份", "pad_save", pd)
        self.kf["pad_load"] = key_row("还原", "pad_load", pd)
        self.pad_status = note("", parent=pd)
        note("至少两个键，按住0.6秒才触发，多按了别的键不算。手柄键游戏照样收得到。", parent=pd)

        self.input_boxes = {"km": km, "pad": pd}
        self._show_input_box()

        # ---- 提示 ----
        section("提示", "bell")
        row("提示音", lambda r: Toggle(r, self.cfg["sound"], lambda v: self.set_cfg(sound=v)))
        row("操作成功弹出", lambda r: Toggle(r, self.cfg["overlay"], lambda v: self.set_cfg(overlay=v)))
        prev = tk.Frame(p, bg=C["panel"])
        prev.pack(fill="x", padx=pad, pady=(S(4), 0))
        Button(prev, "预览备份", command=lambda: self._feedback("已备份", "20261024_183012", "ok", force=True)) \
            .pack(side="left")
        Button(prev, "预览还原", command=lambda: self._feedback("已还原", "打完加斯科因神父", "load", force=True)) \
            .pack(side="left", padx=(S(8), 0))
        note("游戏要开「无边框窗口」才看得到弹窗，独占全屏会盖住它。")

        # ---- 快照 ----
        section("快照", "stack")
        row("最多保留", lambda r: Stepper(r, self.cfg["keep"], MIN_KEEP, 50, 1,
                                     lambda v: self.set_cfg(keep=v), unit=" 份"))
        note(f"锁住的也算在里面。超过这个数时，再备份会从最旧的没锁的开始自动删。最多锁{MAX_LOCKED}个，锁住的不会被删。")

        tk.Label(p, text=VERSION, font=F(8), bg=C["panel"], fg=C["faint"]).pack(pady=(S(28), S(16)))

    # ================= 刷新 =================
    def refresh_all(self):
        self.info = self.be.detect()
        ok = self.info.found
        self.pill_dot.configure(fg=C["ok"] if ok else C["err"])
        self.pill_txt.configure(text="已找到存档" if ok else "未找到存档")
        self.btn_save.set_disabled(not ok)
        self.btn_load.set_disabled(not ok)
        self._render_card()
        self._render_list()
        self._render_keys()

    def _render_keys(self):
        for k, f in self.kf.items():
            if self.recording != k:
                f.show(keys.display(self.cfg[k]))
        if self._mode == "pad":
            self.btn_save.set_sub("手柄 " + keys.display(self.cfg["pad_save"]))
            self.btn_load.set_sub("手柄 " + keys.display(self.cfg["pad_load"]))
        else:
            self.btn_save.set_sub("热键 " + keys.display(self.cfg["save_key"]))
            self.btn_load.set_sub("热键 " + keys.display(self.cfg["load_key"]))

    def _show_input_box(self):
        for name, box in self.input_boxes.items():
            if name == self._mode:
                box.pack(fill="x")
            else:
                box.pack_forget()

    def redetect(self):
        self.refresh_all()
        self.flash("已重新检测", "ok" if self.info.found else "err")

    def set_cfg(self, **kw):
        self.be.set_config(**kw)
        self.cfg.update(kw)
        if kw.keys() & {"save_key", "load_key", "pad_save", "pad_load"}:
            self._apply_binds()
        self._render_keys()

    # ---- 键鼠 / 手柄 自动切换 ----
    # 没插手柄：只能用键鼠。插上手柄：自动切到手柄，除非用户手动选了键鼠（这个选择会记住）。
    # 用户再点一次手柄就恢复成"插上就自动切"。
    def _pad_connected(self):
        return bool(self.pad and self.pad.available and self.pad.connected)

    def _wanted_mode(self):
        return "pad" if self.cfg.get("input_pref") == "auto" and self._pad_connected() else "km"

    def _sync_mode(self, why=None):
        new = self._wanted_mode()
        if new == self._mode:
            return
        self.stop_record()
        self._mode = new
        self.input_seg.set(new)
        self._show_input_box()
        self._apply_binds()
        self._render_keys()
        if why:
            self.flash(why, "ok")

    def _on_mode_click(self, v):
        if v == "pad":
            if not self._pad_connected():
                self.input_seg.set(self._mode)
                return self.flash("没检测到手柄，插上手柄才能切换", "err")
            self.set_cfg(input_pref="auto")
            self._sync_mode("已切到手柄热键，键鼠那套停用")
        else:
            if self._mode == "km":
                return
            self.set_cfg(input_pref="km")
            self._sync_mode("已切到键鼠热键，手柄插着也不会再自动切过去")

    # ================= 动作 =================
    def do_save(self, from_hotkey=False):
        if not self.info.found:
            self.flash("没找到存档，备份不了", "err")
            return self._feedback("备份失败", "没找到存档", "err", from_hotkey)
        try:
            snap, reused = self.be.save()
        except (OSError, LookupError) as e:
            self.flash(f"备份失败：{e}", "err")
            return self._feedback("备份失败", str(e), "err", from_hotkey)
        self._render_list()
        if reused:
            self.flash(f"存档没变化，刷新了「{snap.name}」的时间", "ok")
            self._feedback("存档没变化", "已刷新上一份的时间", "ok", from_hotkey)
        else:
            self.flash(f"已备份：{snap.name}", "ok")
            self._feedback("已备份", snap.name, "ok", from_hotkey)

    def do_load(self, snap, ask=False, from_hotkey=False):
        if not self.info.found:
            self.flash("没找到存档，还原不了", "err")
            return self._feedback("还原失败", "没找到存档", "err", from_hotkey)

        def go():
            try:
                target = self.be.load(snap.id if snap else None)
            except (OSError, LookupError) as e:
                self.flash(f"还原失败：{e}", "err")
                self._feedback("还原失败", str(e), "err", from_hotkey)
                return
            self.info = self.be.detect()
            self._render_card()
            self.flash(f"已还原：{target.name}", "ok")
            self._feedback("已还原", target.name, "load", from_hotkey)

        if not ask:
            return go()
        dialogs.confirm(self.root, "还原快照", f"还原到「{snap.name}」？", ok_text="还原", on_ok=go,
                        detail="当前的存档会被这份快照直接覆盖。\n还原之前请先退回标题画面，或者退出游戏。")

    def do_rename(self, s, label):
        """原地改名：名字那一格直接变成输入框。回车或点别处保存，Esc 取消。"""
        if getattr(label, "_editing", False):
            return
        label._editing = True
        maxlen = 20
        vcmd = (self.root.register(lambda p: len(p) <= maxlen), "%P")
        box = tk.Frame(label.master, bg=C["accent"])      # 1px 橙色边框，表示正在编辑
        box._keep_bg = True
        entry = tk.Entry(box, font=F(10), bg=C["panel2"], fg=C["text"], relief="flat",
                         insertbackground=C["text"], selectbackground=C["blue"], selectforeground=C["text"],
                         validate="key", validatecommand=vcmd)
        entry._keep_bg = True
        entry.insert(0, s.name)
        entry.pack(fill="x", padx=1, pady=1, ipady=S(1), ipadx=S(4))
        info = label.grid_info()
        label.grid_remove()
        box.grid(row=info["row"], column=info["column"], sticky="ew", padx=(0, S(10)))
        done = []

        def finish(save):
            if done:
                return
            done.append(True)
            new = entry.get().strip()
            box.destroy()
            label._editing = False
            label.grid()
            if not save or new == s.name:
                return
            if not new:
                return self.flash("名字不能是空的，没改", "err")
            try:
                self.be.rename(s.id, new)
            except (OSError, LookupError) as e:
                return self.flash(f"改名失败：{e}", "err")
            s.name = new
            label.configure(text=new, font=F(10), fg=C["text"])   # 改过名就不再是灰色的时间戳样式
            self.flash(f"已改名为「{new}」", "ok")

        entry.bind("<Return>", lambda _e: finish(True))
        entry.bind("<KP_Enter>", lambda _e: finish(True))
        entry.bind("<Escape>", lambda _e: finish(False))
        entry.bind("<FocusOut>", lambda _e: finish(True))
        entry.focus_set()
        entry.select_range(0, "end")
        entry.icursor("end")

    def do_lock(self, s):
        try:
            self.be.set_locked(s.id, not s.locked)
        except (OSError, LookupError) as e:
            return self.flash(str(e), "err")
        self._render_list()
        self.flash(f"已锁住「{s.name}」，不会被自动删" if not s.locked else f"已解锁「{s.name}」", "ok")

    def do_delete(self, s):
        def ok():
            try:
                self.be.delete(s.id)
            except (OSError, LookupError) as e:
                return self.flash(f"删除失败：{e}", "err")
            self._render_list()
            self.flash(f"已删除「{s.name}」", "ok")

        dialogs.confirm(self.root, "删除快照", f"删除「{s.name}」？", ok_text="删除", on_ok=ok, danger=True,
                        detail=("这个快照锁着。" if s.locked else "") + "删掉就找不回来了。")

    def _feedback(self, title, sub, kind, from_hotkey=False, force=False):
        """热键触发时给提示音和浮窗。在窗口里点按钮的时候窗口就在眼前，不用再弹。"""
        if not (from_hotkey or force):
            return
        if self.cfg["sound"]:
            sound.play({"ok": "save", "load": "load", "err": "error"}[kind])
        if self.cfg["overlay"] or force:
            toast.show(self.root, title, sub, kind)

    def flash(self, text, kind="info"):
        col = {"ok": C["ok"], "err": C["err"], "info": C["dim"]}[kind]
        self.status.configure(text=text, fg=col)
        if self._flash_timer:
            self.root.after_cancel(self._flash_timer)
        self._flash_timer = self.root.after(5000, lambda: self.status.configure(text=""))

    def _open(self, path):
        try:
            os.startfile(path)
        except OSError:
            self.flash(f"打不开：{path}", "err")

    # ================= 按键录制 =================
    def start_record(self, which):
        is_pad = which.startswith("pad_")
        if is_pad and (self.pad is None or not self.pad.available):
            return self.flash("这台电脑上用不了 XInput，录不了手柄", "err")
        if is_pad != (self._mode == "pad"):
            return
        if not is_pad and self.hk is None:
            return self.flash("热键没装上，录不了：" + (self.hk_error or ""), "err")
        self.stop_record()
        self.recording = which
        self.kf[which].show("按住组合再松开…" if is_pad else "按下按键…", "rec")
        self._hint_rec()
        # 录制是钩子在做：下一次按键不触发备份/还原，直接报回来。键盘和鼠标侧键都能录
        # 录手柄时键盘钩子只听 Esc，好让 Esc 也能取消
        if self.hk:
            self.hk.record(True, cancel_only=is_pad)
        if is_pad:
            self.pad.record(True)
        self._rec_timer = self.root.after(20000, self.stop_record)  # 兜底：20 秒没按就放弃

    def stop_record(self):
        if self._rec_timer:
            self.root.after_cancel(self._rec_timer)
            self._rec_timer = None
        if self.recording:
            self.recording = None
            if self.hk:
                self.hk.record(False)
            if self.pad:
                self.pad.record(False)
            self._hint_idle()
            self._render_keys()

    def _hint_parts(self, parts):
        for w in self.rec_hint.winfo_children():
            w.destroy()
        for text, col in parts:
            tk.Label(self.rec_hint, text=text, font=F(9, "bold" if col == C["err"] else "normal"),
                     bg=C["panel"], fg=col, padx=0).pack(side="left")

    def _hint_idle(self):
        self._hint_parts([("点按键框，再按键盘键或鼠标侧键/中键。", C["faint"])])

    def _hint_rec(self):
        self._hint_parts([("可以先按住 Ctrl/Shift/Alt，按 ", C["dim"]), ("Esc", C["err"]), (" 取消。", C["dim"])])

    def _poll_hotkeys(self):
        """钩子线程把事件塞进队列，这里在 Tk 线程里取出来处理（Tk 不能跨线程碰）。"""
        for src in (self.hk, self.pad):
            if src is None:
                continue
            for kind, val in src.poll():
                if kind == "fire":
                    if self.recording:
                        continue
                    if val == "save":
                        self.do_save(from_hotkey=True)
                    elif val == "load":
                        self.do_load(None, from_hotkey=True)
                elif self.recording:
                    self._on_recorded(kind, val, from_pad=src is self.pad)
        self._render_pad_status()
        self.root.after(30, self._poll_hotkeys)

    def _render_pad_status(self):
        if self.pad is None or not self.pad.available:
            text, col = "这台电脑上用不了 XInput。", C["err"]
        elif self.pad.connected:
            text, col = f"已连接 {self.pad.connected} 个手柄。", C["ok"]
        else:
            text, col = "没检测到手柄，插上就能用。", C["faint"]
        if self._pad_seen != text:
            first = self._pad_seen is None
            self._pad_seen = text
            self.pad_status.configure(text=text, fg=col)
            self.input_seg.set_dim("pad", not self._pad_connected())
            if not first:
                self._sync_mode("检测到手柄，已切到手柄热键" if self._pad_connected()
                                else "手柄断开了，已切回键鼠热键")

    def _on_recorded(self, kind, spec, from_pad=False):
        which = self.recording
        is_pad = which.startswith("pad_")
        if kind == "rec_cancel":
            return self.stop_record()
        if from_pad != is_pad:
            return            # 录键鼠的时候手柄那边来的消息不算，反过来也一样
        if kind == "rec_bad":
            return self._key_error(which, spec if is_pad else "这个键不支持")
        pairs = {"save_key": "load_key", "load_key": "save_key", "pad_save": "pad_load", "pad_load": "pad_save"}
        other = pairs[which]
        if spec == self.cfg[other]:
            return self._key_error(which, "和" + ("还原" if other in ("load_key", "pad_load") else "备份") + "重复了")
        self.stop_record()
        self.set_cfg(**{which: spec})
        what = "备份" if which in ("save_key", "pad_save") else "还原"
        self.flash(f"{'手柄' if is_pad else ''}{what}热键改成了 {keys.display(spec)}", "ok")

    def _key_error(self, which, msg):
        """报错一下，然后接着录。"""
        f = self.kf[which]
        f.show(msg, "err")

        def resume():
            if self.recording == which:
                is_pad = which.startswith("pad_")
                f.show("按住组合再松开…" if is_pad else "按下按键…", "rec")
                if self.hk:
                    self.hk.record(True, cancel_only=is_pad)
                if is_pad:
                    self.pad.record(True)

        self.root.after(1200, resume)

    def _apply_binds(self):
        """键鼠和手柄只开一套：没选中的那套绑空，按了什么都不会触发，键鼠也不会再拦截任何按键。"""
        use_pad = self._mode == "pad"
        if self.hk:
            self.hk.set_binds({} if use_pad else {"save": self.cfg["save_key"], "load": self.cfg["load_key"]})
        if self.pad:
            self.pad.set_binds({"save": self.cfg["pad_save"], "load": self.cfg["pad_load"]} if use_pad else {})

    def _close(self):
        for src in (self.hk, self.pad):
            if src:
                src.stop()
        self.root.destroy()
