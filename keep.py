"""Pictures kept in the badge's flash: at most MAX_KEEP resized copies, so the
gallery still has something to show with no SD card (the HDMI hexpansion and an
SD hexpansion can't both be fitted). The oldest is dropped when it is full.

    keep.add(path)      -> "kept" / "replaced" / "already" / "failed"
    keep.remove(path)
    keep.has(path)
    keep.count()
"""
import os
from . import scanner, storage, thumbs, imginfo

MAX_KEEP = 10
SIZES = (240, 480, 720)   # longest side of a kept copy; bigger ones are for the HDMI display
size = 240                # the one in use (the Settings tile changes it)
MIN_FREE = 300 * 1024     # flash that must stay free
MAX_COPY = 96 * 1024   # without imgtool, a small JPEG this size or less is copied as it is
ORDER = storage.KEPT + "/.order"


def _name(path):
    return path.rpartition("/")[2]


def _kname(path):
    n = _name(path)
    return n if n.lower().endswith((".jpg", ".jpeg")) else n + ".jpg"


def _order():
    try:
        with open(ORDER) as f:
            names = [l.strip() for l in f if l.strip()]
    except OSError:
        names = []
    have = [_name(p) for p in scanner.list_images(storage.KEPT)]
    out = [n for n in names if n in have]
    return out + [n for n in have if n not in out]


def _write_order(names):
    try:
        with open(ORDER, "w") as f:
            f.write("\n".join(names) + "\n")
    except OSError:
        pass


def count():
    return len(scanner.list_images(storage.KEPT))


def has(path):
    if path.startswith(storage.KEPT + "/"):
        return True
    return any(scanner.exists(storage.KEPT + "/" + n) for n in (_name(path), _kname(path)))


def _remove(p):
    try:
        os.remove(p)
    except OSError:
        pass


def remove(path):
    """Take a kept picture out of flash (path may be the original or the kept copy)."""
    if not path.startswith(storage.KEPT + "/"):
        for n in (_name(path), _kname(path)):
            if scanner.exists(storage.KEPT + "/" + n):
                path = storage.KEPT + "/" + n
                break
        else:
            return
    _remove(path)
    _remove(scanner.thumb_path(path))
    for px in SIZES:  # copies the viewer made to draw a big kept picture on the badge
        _remove("%s/.view%d/%s.jpg" % (storage.KEPT, px, _name(path)))
    _write_order([n for n in _order() if n != _name(path)])


def _copy(src, dst):
    tmp = dst + ".part"
    buf = bytearray(2048)
    try:
        with open(src, "rb") as f, open(tmp, "wb") as g:
            while True:
                n = f.readinto(buf)
                if not n:
                    break
                g.write(memoryview(buf)[:n])
        os.rename(tmp, dst)
    except OSError:
        _remove(tmp)
        return False
    return True


def free():
    """Bytes free in the flash (a big number if it can't be told)."""
    try:
        st = os.statvfs(storage.KEPT_ROOT if scanner.exists(storage.KEPT_ROOT) else "/")
        return st[0] * st[3]
    except (OSError, AttributeError):
        return 1 << 30


def add(path):
    if has(path):
        return "already"
    if free() < MIN_FREE:
        return "full"
    storage._mkdirs()
    src = thumbs.shrunk(path, size=size) if thumbs.available else None
    out = storage.KEPT + "/" + _kname(path)
    if src is None:  # no resizer, or it can't do this one: copy only if already small
        dims = imginfo.size(path)
        try:
            small = os.stat(path)[6] <= MAX_COPY
        except OSError:
            small = False
        if not (small and dims and dims[0] * dims[1] <= thumbs.VIEW_MAX ** 2
                and path.lower().endswith((".jpg", ".jpeg"))):
            return "failed"
        src = path
    names = _order()
    dropped = False
    while len(names) >= MAX_KEEP:
        remove(storage.KEPT + "/" + names.pop(0))
        dropped = True
    if not _copy(src, out):
        return "failed"
    names.append(_name(out))
    _write_order(names)
    thumbs.make(out)
    return "replaced" if dropped else "kept"
