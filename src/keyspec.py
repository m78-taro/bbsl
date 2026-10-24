"""热键的写法，界面和后端共用。

存的是规格串，和 Stmsl 一样：num1、ctrl+f5、shift+mouse4、pad_lb+pad_back。
界面上显示成人能看的样子：Num 1、Ctrl + F5、Shift + 下侧键、LB + Back。

键鼠是合在一起的：一个热键 = 若干修饰键（Ctrl/Shift/Alt）+ 一个主键，主键可以是键盘键，也可以是鼠标中键/侧键。
"""

# ---- 键盘主键：Windows 虚拟键码 -> (规格名, 显示名) ----
VK = {}
for i in range(10):
    VK[0x30 + i] = (str(i), str(i))
    VK[0x60 + i] = (f"num{i}", f"Num {i}")
for i in range(26):
    ch = chr(ord("a") + i)
    VK[0x41 + i] = (ch, ch.upper())
for i in range(24):
    VK[0x70 + i] = (f"f{i + 1}", f"F{i + 1}")
VK.update({
    0x6A: ("num*", "Num *"), 0x6B: ("num+", "Num +"), 0x6D: ("num-", "Num -"),
    0x6E: ("num.", "Num ."), 0x6F: ("num/", "Num /"),
    0x20: ("space", "Space"), 0x0D: ("enter", "Enter"), 0x09: ("tab", "Tab"),
    0x08: ("backspace", "Backspace"),
    0x2D: ("insert", "Insert"), 0x2E: ("delete", "Delete"),
    0x24: ("home", "Home"), 0x23: ("end", "End"),
    0x21: ("pageup", "PgUp"), 0x22: ("pagedown", "PgDn"),
    0x25: ("left", "←"), 0x26: ("up", "↑"), 0x27: ("right", "→"), 0x28: ("down", "↓"),
    0x13: ("pause", "Pause"), 0x91: ("scrolllock", "ScrLk"),
    0xC0: ("`", "`"), 0xBD: ("-", "-"), 0xBB: ("=", "="),
    0xDB: ("[", "["), 0xDD: ("]", "]"), 0xDC: ("backslash", "\\"),
    0xBA: (";", ";"), 0xDE: ("'", "'"), 0xBC: (",", ","), 0xBE: (".", "."), 0xBF: ("/", "/"),
})
VK_BY_NAME = {name: vk for vk, (name, _) in VK.items()}

VK_ESCAPE = 0x1B
# 修饰键本身（含左右区分的版本）、Win 键、大小写/数字锁定：录制时按这些不算数，等主键
MODIFIER_VKS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C, 0x14, 0x90}

# ---- 修饰键 ----
MODS = [("ctrl", "Ctrl", 0x11), ("shift", "Shift", 0x10), ("alt", "Alt", 0x12)]
MOD_ORDER = [m for m, _, _ in MODS]

# ---- 鼠标主键 ----
# 左右键不让绑：绑了游戏里就没法正常点了。
# mouse4 = XBUTTON1 = 浏览器里的"后退"，大多数鼠标上是靠后/靠下的那颗侧键
# mouse5 = XBUTTON2 = "前进"，靠前/靠上的那颗
MOUSE = {"mouse3": "中键", "mouse4": "下侧键", "mouse5": "上侧键"}

# ---- 手柄（XInput）----
PAD = {
    "pad_a": "A", "pad_b": "B", "pad_x": "X", "pad_y": "Y",
    "pad_lb": "LB", "pad_rb": "RB", "pad_lt": "LT", "pad_rt": "RT",
    "pad_back": "Back", "pad_start": "Start", "pad_ls": "LS", "pad_rs": "RS",
    "pad_up": "↑", "pad_down": "↓", "pad_left": "←", "pad_right": "→",
}

_DISPLAY = {spec: disp for spec, disp in VK.values()}
_DISPLAY.update({m: d for m, d, _ in MODS})
_DISPLAY.update(MOUSE)
_DISPLAY.update(PAD)


def build(mods, main):
    """修饰键按固定顺序排，这样 shift+ctrl+x 和 ctrl+shift+x 是同一个串，比较重复时不会漏。"""
    return "+".join([m for m in MOD_ORDER if m in mods] + [main])


def parse(spec):
    """'shift+mouse4' -> (frozenset({'shift'}), 'mouse4')。认不出来返回 None。"""
    if not spec:
        return None
    parts = spec.split("+")
    mods, main = parts[:-1], parts[-1]
    if any(m not in MOD_ORDER for m in mods):
        return None
    if main not in VK_BY_NAME and main not in MOUSE:
        return None
    return frozenset(mods), main


def display(spec):
    if not spec:
        return "未设置"
    return " + ".join(_DISPLAY.get(p, p) for p in spec.split("+"))
