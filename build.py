r"""打包：python build.py

src\   源码
dist\  能直接用的版本：bbsl\ 文件夹（免安装，带 README.md 和精简版 README.txt）和它的 zip
打包过程的临时文件放在 build\，打完就删。
"""
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
DIST = os.path.join(ROOT, "dist")
WORK = os.path.join(ROOT, "build")
ICON = os.path.join(ROOT, "private", "app.ico")
VERSION = "v0.1"


def main():
    shutil.rmtree(os.path.join(DIST, "bbsl"), ignore_errors=True)
    # 图标不在仓库里（private\ 被 .gitignore 忽略了）。有就打进去，没有就用默认图标
    icon = []
    if os.path.isfile(ICON):
        icon = ["--icon", ICON,                                 # exe 文件的图标
                "--add-data", ICON + os.pathsep + "assets"]     # 窗口和任务栏图标，运行时要读
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", os.path.join(SRC, "main.py"),
        "--name", "bbsl", "--onedir", "--windowed", "--noconfirm", "--clean",
        "--paths", SRC,
        "--distpath", DIST, "--workpath", os.path.join(WORK, "work"), "--specpath", WORK,
        "--exclude-module", "PIL", "--exclude-module", "numpy",
        *icon,
    ])
    shutil.rmtree(WORK, ignore_errors=True)

    # 说明文件跟着一起发：完整版 README.md，和给玩家看的精简版 README.txt。
    # txt 存成带 BOM 的 UTF-8、Windows 换行，老版本记事本打开也不会乱码
    out = os.path.join(DIST, "bbsl")
    shutil.copy2(os.path.join(ROOT, "README.md"), out)
    with open(os.path.join(ROOT, "docs", "README.txt"), encoding="utf-8") as f:
        text = f.read()
    with open(os.path.join(out, "README.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(text)

    zip_path = os.path.join(DIST, f"bbsl-{VERSION}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _dirs, files in os.walk(os.path.join(DIST, "bbsl")):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, DIST))
    print(f"完成：{zip_path}（{os.path.getsize(zip_path) / 1024 / 1024:.1f} MB）")


if __name__ == "__main__":
    main()
