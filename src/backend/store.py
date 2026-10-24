r"""真后端：找存档、备份、还原、管理快照、存设置。

目录结构（都在工具自己的目录下）：
    bbsl_config.json
    bbsl_backups\
        20261024_183012\
            meta.json          名字、时间、类型、内容指纹
            savedata\...       原样复制的 user\savedata
"""
import datetime as dt
import hashlib
import json
import os
import shutil

from .stub import AUTO_NAME, DEFAULT_CONFIG, MAX_LOCKED, MIN_KEEP, SaveInfo, Snapshot

BACKUP_DIR = "bbsl_backups"
CONFIG_FILE = "bbsl_config.json"
GAME_SAVE_DIR = "SPRJ0005"     # 血源的存档目录名，用它确认找到的 savedata 确实是血源的
SEARCH_UP = 3                  # 从工具目录往上找几层
SLOTS = 10                     # userdata0000 ~ userdata0009 是 10 个角色槽位
NAME_OFFSET = 0x9E88           # 角色名（UTF-16）在 userdataXXXX 里的位置，见 _slot_name 的说明
TMP_SUFFIX = ".bbsl_tmp"
BUSY = "存档文件被占用，先退到标题画面或关掉游戏再试"


class Backend:
    def __init__(self, tool_dir):
        tool_dir = os.path.normpath(os.path.abspath(tool_dir))
        self.tool_dir = tool_dir
        self.backup_root = os.path.join(tool_dir, BACKUP_DIR)
        self.config_path = os.path.join(tool_dir, CONFIG_FILE)
        self.config = dict(DEFAULT_CONFIG)
        self._load_config()
        self.savedata = None       # 找到的 user\savedata
        self.game_dirs = []        # savedata 下面所有的 SPRJ0005

    # ================= 设置 =================
    def _load_config(self):
        try:
            with open(self.config_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.config.update({k: v for k, v in saved.items() if k in DEFAULT_CONFIG})
        except (OSError, ValueError):
            pass

    def get_config(self):
        return dict(self.config)

    def set_config(self, **kw):
        self.config.update(kw)
        tmp = self.config_path + TMP_SUFFIX
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.config_path)
        except OSError:
            pass   # 存不了设置不影响 S/L，下次启动回到上次能存下的状态

    # ================= 找存档 =================
    def detect(self):
        self.savedata, self.game_dirs = None, []
        d = self.tool_dir
        for _ in range(SEARCH_UP + 1):
            sd = os.path.join(d, "user", "savedata")
            dirs = _find_game_dirs(sd)
            if dirs:
                self.savedata, self.game_dirs = sd, dirs
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        if not self.savedata:
            return SaveInfo(False, self.tool_dir)

        chars, newest = [], None
        for gd in self.game_dirs:
            for i in range(SLOTS):
                p = os.path.join(gd, f"userdata{i:04d}")
                if _slot_used(p):
                    chars.append((i + 1, _slot_name(p) or f"槽位 {i + 1}"))
            for name in os.listdir(gd):
                try:
                    t = os.path.getmtime(os.path.join(gd, name))
                except OSError:
                    continue
                newest = t if newest is None else max(newest, t)
        return SaveInfo(True, self.tool_dir, save_dir=self.game_dirs[0], characters=chars,
                        mtime=dt.datetime.fromtimestamp(newest).replace(microsecond=0) if newest else None)

    # ================= 快照 =================
    def snapshot_dir(self):
        os.makedirs(self.backup_root, exist_ok=True)
        return self.backup_root

    def snapshots(self):
        out = []
        try:
            names = os.listdir(self.backup_root)
        except OSError:
            return out
        for sid in names:
            if sid.startswith("."):
                continue       # .tmp_ 开头的是正在写或者上次写到一半的
            meta = _read_meta(os.path.join(self.backup_root, sid))
            if meta is None or not os.path.isdir(os.path.join(self.backup_root, sid, "savedata")):
                continue
            try:
                t = dt.datetime.strptime(meta["time"], "%Y-%m-%d %H:%M:%S")
            except (KeyError, ValueError):
                continue
            out.append(Snapshot(sid, meta.get("name") or sid, t, meta.get("size", 0), bool(meta.get("locked"))))
        out.sort(key=lambda s: s.time, reverse=True)
        return out

    def save(self):
        """备份当前存档。返回 (快照, 是否复用了已有的)。

        内容和某个"还没改过名"的快照完全一样时，不再多存一份，只把那份的时间刷新成现在。
        改过名的、锁住的快照是用户特意留的，永远不拿来复用。
        存完之后，没锁的快照超过上限的，从最旧的开始删。
        """
        self._need_save()
        root = self.snapshot_dir()
        now = dt.datetime.now().replace(microsecond=0)
        tmp = os.path.join(root, f".tmp_{now:%Y%m%d_%H%M%S}_{os.getpid()}")
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            digest, size = _copy_tree(self.savedata, os.path.join(tmp, "savedata"))
        except PermissionError:
            shutil.rmtree(tmp, ignore_errors=True)
            raise OSError(BUSY)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

        for s in self.snapshots():
            meta = _read_meta(os.path.join(root, s.id)) or {}
            if meta.get("hash") == digest and s.auto_named and not s.locked:
                shutil.rmtree(tmp, ignore_errors=True)
                meta["name"] = now.strftime(AUTO_NAME)
                meta["time"] = now.strftime("%Y-%m-%d %H:%M:%S")
                _write_meta(os.path.join(root, s.id), meta)
                return self._get(s.id), True

        sid = now.strftime(AUTO_NAME)
        n = 2
        while os.path.exists(os.path.join(root, sid)):
            sid = f"{now:%Y%m%d_%H%M%S}_{n}"
            n += 1
        _write_meta(tmp, {"name": now.strftime(AUTO_NAME), "time": now.strftime("%Y-%m-%d %H:%M:%S"),
                          "hash": digest, "size": size})
        os.replace(tmp, os.path.join(root, sid))
        self._prune()
        return self._get(sid), False

    def set_locked(self, snap_id, on):
        d = self._snap_path(snap_id)
        meta = _read_meta(d)
        if meta is None:
            raise LookupError("这个快照已经不在了")
        if on and not meta.get("locked") and sum(1 for s in self.snapshots() if s.locked) >= MAX_LOCKED:
            raise LookupError(f"最多锁 {MAX_LOCKED} 个，先解锁一个")
        meta["locked"] = bool(on)
        _write_meta(d, meta)

    def _prune(self):
        """快照总数（锁住的也算）超过 keep 份时，从最旧的没锁的开始删。锁住的永远不删。"""
        keep = max(MIN_KEEP, int(self.config.get("keep", 20)))
        snaps = self.snapshots()
        extra = len(snaps) - keep
        for s in reversed(snaps):          # 从最旧的开始
            if extra <= 0:
                break
            if not s.locked:
                shutil.rmtree(os.path.join(self.backup_root, s.id), ignore_errors=True)
                extra -= 1

    def load(self, snap_id=None):
        """还原：用快照直接覆盖当前存档。snap_id 为空就还原最新的那份。返回还原的快照。"""
        self._need_save()
        snaps = self.snapshots()
        if snap_id is None:
            if not snaps:
                raise LookupError("还没有备份，先备份一次")
            target = snaps[0]
        else:
            target = next((s for s in snaps if s.id == snap_id), None)
            if target is None:
                raise LookupError("这个快照已经不在了")
        _mirror(os.path.join(self.backup_root, target.id, "savedata"), self.savedata)
        return target

    def rename(self, snap_id, name):
        d = self._snap_path(snap_id)
        meta = _read_meta(d)
        if meta is None:
            raise LookupError("这个快照已经不在了")
        meta["name"] = name
        _write_meta(d, meta)

    def delete(self, snap_id):
        shutil.rmtree(self._snap_path(snap_id))

    # ================= 内部 =================
    def _need_save(self):
        if not self.savedata or not os.path.isdir(self.savedata):
            raise LookupError("没找到存档")

    def _snap_path(self, snap_id):
        # id 只允许是 bbsl_backups 下一层的文件夹名，防止被拼出别的路径
        if not snap_id or os.sep in snap_id or "/" in snap_id or snap_id in (".", "..") or snap_id.startswith("."):
            raise LookupError("快照 id 不对")
        return os.path.join(self.backup_root, snap_id)

    def _get(self, sid):
        return next(s for s in self.snapshots() if s.id == sid)


# ================= 文件操作 =================
def _find_game_dirs(savedata):
    """savedata\\<用户>\\<游戏编号>\\SPRJ0005。不认游戏编号，不同版本的血源编号不一样。"""
    found = []
    try:
        users = os.listdir(savedata)
    except OSError:
        return found
    for u in users:
        up = os.path.join(savedata, u)
        try:
            titles = os.listdir(up)
        except OSError:
            continue
        for t in titles:
            gd = os.path.join(up, t, GAME_SAVE_DIR)
            if os.path.isdir(gd):
                found.append(gd)
    return found


def _slot_used(path):
    """空槽位整个文件都是 0，有角色的开头就有数据。"""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    return any(head)


def _slot_name(path):
    """角色名。这个位置是对比了同一个角色几个不同时间的存档找到的，一直没变过，
    但不保证所有角色、所有版本都在这里 —— 读出来不像名字就当没有，界面显示"槽位 N"。"""
    try:
        with open(path, "rb") as f:
            f.seek(NAME_OFFSET)
            raw = f.read(34)
    except OSError:
        return None
    name = raw.decode("utf-16-le", "ignore").split("\x00")[0]
    if 1 <= len(name) <= 16 and name.isprintable():
        return name
    return None


def _list_files(src):
    files = []
    for root, _dirs, names in os.walk(src):
        for n in names:
            if not n.endswith(TMP_SUFFIX):
                files.append(os.path.relpath(os.path.join(root, n), src))
    files.sort()
    return files


def _copy_tree(src, dst=None):
    """复制整个目录，顺便算内容指纹。dst 为空就只算指纹、不复制。
    指纹只看相对路径和内容，跟时间无关，同样的存档指纹一定一样。"""
    h = hashlib.sha256()
    total = 0
    if dst:
        os.makedirs(dst, exist_ok=True)
    for rel in _list_files(src):
        with open(os.path.join(src, rel), "rb") as f:
            data = f.read()
        if dst:
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as f:
                f.write(data)
            shutil.copystat(os.path.join(src, rel), out)
        h.update(rel.replace(os.sep, "/").encode("utf-8") + b"\0")
        h.update(hashlib.sha256(data).digest())
        total += len(data)
    return h.hexdigest(), total



def _mirror(src, dst):
    """让 dst 变得和 src 一模一样。

    分两步：先把所有文件写成临时文件，全部写成功了再统一换上去。
    这样中途出错（比如磁盘满）时，正本一个都没动。
    换之前还会试着以写方式打开每个正本，游戏要是正锁着文件，就在动手之前停下来。
    """
    files = []
    for root, _dirs, names in os.walk(src):
        for n in names:
            files.append(os.path.relpath(os.path.join(root, n), src))

    for rel in files:
        p = os.path.join(dst, rel)
        if os.path.exists(p):
            try:
                with open(p, "r+b"):
                    pass
            except OSError:
                raise OSError(BUSY)

    temps = []
    try:
        for rel in files:
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            tmp = out + TMP_SUFFIX
            shutil.copy2(os.path.join(src, rel), tmp)
            temps.append((tmp, out))
    except OSError:
        for tmp, _ in temps:
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    for tmp, out in temps:
        os.replace(tmp, out)

    keep = {os.path.normcase(r) for r in files}
    for root, _dirs, names in os.walk(dst):
        for n in names:
            rel = os.path.relpath(os.path.join(root, n), dst)
            if os.path.normcase(rel) not in keep:
                try:
                    os.remove(os.path.join(root, n))
                except OSError:
                    pass


def _read_meta(d):
    try:
        with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_meta(d, meta):
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "meta.json")
    with open(p + TMP_SUFFIX, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(p + TMP_SUFFIX, p)
