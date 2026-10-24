"""假后端：只给界面喂数据，不碰任何真实文件。

真后端要实现同样的方法，界面那边就不用改。
"""
import copy
import datetime as dt
import os
import random
from dataclasses import dataclass, field

AUTO_NAME = "%Y%m%d_%H%M%S"

DEFAULT_CONFIG = {
    "save_key": "shift+mouse4",
    "load_key": "shift+mouse5",
    "input_pref": "auto",     # auto：插着手柄就用手柄、没插用键鼠；km：用户手动选了键鼠，插着手柄也不切
    "pad_save": "pad_lb+pad_back",
    "pad_load": "pad_rb+pad_start",
    "sound": True,
    "overlay": True,
    "keep": 20,               # 快照最多留几份（锁住的也算在内），超了从最旧的没锁的开始删
}

MAX_LOCKED = 5                # 最多锁几个
MIN_KEEP = MAX_LOCKED + 1     # 上限最少这么多：锁满了也得给新备份留一个位置，不然刚存完就被删


@dataclass
class SaveInfo:
    found: bool
    search_from: str                 # 从哪儿开始往上找的（工具所在目录）
    save_dir: str = ""               # ...\user\savedata\1\CUSA00207\SPRJ0005
    characters: list = field(default_factory=list)   # [(槽位号, 角色名), ...]
    mtime: dt.datetime = None        # 存档最后写入时间


@dataclass
class Snapshot:
    id: str
    name: str
    time: dt.datetime
    size: int           # 字节数
    locked: bool = False    # 锁住的不会被自动删，也不会被"内容一样就复用"改掉

    @property
    def auto_named(self):
        """名字还是默认时间戳 —— 说明用户没改过。"""
        try:
            dt.datetime.strptime(self.name, AUTO_NAME)
            return True
        except ValueError:
            return False


class FakeBackend:
    def __init__(self, missing=False):
        self.missing = missing
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        now = dt.datetime.now().replace(microsecond=0)
        seeds = [("打完加斯科因神父", 3), (None, 14), ("大教堂区 · 灯前", 47), (None, 52), (None, 95),
                 ("亚哈古尔 被抓前", 180), (None, 310)]
        self.snaps = []
        for i, (name, mins) in enumerate(seeds):
            t = now - dt.timedelta(minutes=mins)
            self.snaps.append(Snapshot(str(i), name or t.strftime(AUTO_NAME), t, random.randint(14_990_000, 15_010_000),
                                       locked=name is not None and mins > 100))
        self._next = len(seeds)

    # ---- 存档检测 ----
    def detect(self):
        here = os.path.dirname(os.path.abspath(__file__))
        if self.missing:
            return SaveInfo(False, here)
        return SaveInfo(
            True, here,
            save_dir=r"G:\血源诅咒\BloodbornePC\user\savedata\1\CUSA00207\SPRJ0005",
            characters=[(1, "QAQ")],
            mtime=dt.datetime.now().replace(microsecond=0) - dt.timedelta(minutes=2),
        )

    # ---- 快照 ----
    def snapshots(self):
        return sorted(self.snaps, key=lambda s: s.time, reverse=True)

    def save(self):
        """返回 (快照, 是否复用)。复用 = 存档内容和某个未改名的快照一样，只刷新它的时间。"""
        now = dt.datetime.now().replace(microsecond=0)
        if random.random() < 0.25:
            for s in self.snapshots():
                if s.auto_named and not s.locked:
                    s.time, s.name = now, now.strftime(AUTO_NAME)
                    return s, True
        s = Snapshot(str(self._next), now.strftime(AUTO_NAME), now, random.randint(14_990_000, 15_010_000))
        self._next += 1
        self.snaps.append(s)
        extra = len(self.snaps) - max(MIN_KEEP, int(self.config["keep"]))
        for x in reversed(self.snapshots()):
            if extra <= 0:
                break
            if not x.locked:
                self.snaps.remove(x)
                extra -= 1
        return s, False

    def set_locked(self, snap_id, on):
        if on and sum(1 for s in self.snaps if s.locked) >= MAX_LOCKED:
            raise LookupError(f"最多锁 {MAX_LOCKED} 个，先解锁一个")
        for s in self.snaps:
            if s.id == snap_id:
                s.locked = on

    def load(self, snap_id=None):
        """还原。snap_id 为空就还原最新的那份。返回还原的快照。"""
        snaps = self.snapshots()
        if snap_id is None:
            target = snaps[0] if snaps else None
        else:
            target = next((s for s in snaps if s.id == snap_id), None)
        if target is None:
            raise LookupError("没有可以还原的快照")
        return target

    def rename(self, snap_id, name):
        for s in self.snaps:
            if s.id == snap_id:
                s.name = name

    def delete(self, snap_id):
        self.snaps = [s for s in self.snaps if s.id != snap_id]

    def snapshot_dir(self):
        return os.path.dirname(os.path.abspath(__file__))

    # ---- 设置 ----
    def get_config(self):
        return dict(self.config)

    def set_config(self, **kw):
        self.config.update(kw)

