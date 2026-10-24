"""bbsl 入口。

    python main.py                  正常启动
    python main.py --demo           用假数据看界面，不碰任何存档
    python main.py --demo --missing 假数据 + "没找到存档"的样子
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import tkinter as tk

from backend.gamepad import Gamepad
from backend.hotkeys import Hotkeys
from ui import sound, theme
from ui.app import App

MUTEX = "Local\\bbsl_single_instance"
TITLE = "bbsl"


def tool_dir():
    """打包成 exe 后是 exe 所在目录；直接跑源码时是 main.py 所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def asset(name):
    """打包时塞进程序里的资源文件（在 _internal 下面，PyInstaller 的 _MEIPASS）。
    图标不随源码发布，直接跑源码时找不到，就用默认图标。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


def already_running():
    """只允许开一个：两个都挂着钩子的话，按一下会备份两份。
    已经开着的话，把那个窗口叫到前面来。"""
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.CreateMutexW.restype = wt.HANDLE
    handle = k32.CreateMutexW(None, False, MUTEX)
    if k32.GetLastError() != 183:   # ERROR_ALREADY_EXISTS
        return handle, False

    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        title, cls = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(64)
        u32.GetWindowTextW(hwnd, title, 64)
        u32.GetClassNameW(hwnd, cls, 64)
        # 只认 Tk 的窗口，免得把资源管理器里一个叫 bbsl 的文件夹窗口当成它
        if title.value == TITLE and cls.value == "TkTopLevel":
            found.append(hwnd)
            return False
        return True

    u32.EnumWindows(each, 0)
    for hwnd in found:
        u32.ShowWindow(hwnd, 9)          # SW_RESTORE
        u32.SetForegroundWindow(hwnd)
    return handle, True


def main():
    demo = "--demo" in sys.argv
    _mutex, running = already_running()
    if running:
        return

    theme.enable_dpi_awareness()
    root = tk.Tk()
    try:
        root.iconbitmap(default=asset("app.ico"))   # 任务栏和 Alt+Tab 里的图标
    except tk.TclError:
        pass
    theme.init(root)
    sound.init(tool_dir())

    if demo:
        from backend.stub import FakeBackend
        be = FakeBackend(missing="--missing" in sys.argv)
    else:
        from backend.store import Backend
        be = Backend(tool_dir())

    hk = Hotkeys()
    hk_ok = hk.start()
    pad = Gamepad()
    pad.start()
    App(root, be, hk if hk_ok else None, hk.error, pad)
    root.mainloop()


if __name__ == "__main__":
    main()
