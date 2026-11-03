"""Slideshow staging in PSRAM: a small RAM disk holding the next few shrunk
pictures, so the slideshow doesn't wait on the SD card between slides. The
disk is an ordinary bytearray (a big allocation, so it lands in PSRAM).
ctx.image() only takes a file path, hence a RAM *disk* and not just buffers.

If the firmware can't mount it, or drawing from it fails, `enabled` goes False
and the slideshow reads straight from the card.
"""
import os

MOUNT = "/gallery_ram"
BLOCKS = 1024          # x 512 bytes = 512 KB
enabled = True
_files = {}            # source path -> path in the RAM disk
_mounted = False


class _RAM:
    def __init__(self, blocks):
        self.data = bytearray(blocks * 512)
        self.blocks = blocks

    def readblocks(self, n, buf, off=0):
        a = n * 512 + off
        buf[:] = self.data[a:a + len(buf)]

    def writeblocks(self, n, buf, off=0):
        a = n * 512 + off
        self.data[a:a + len(buf)] = buf

    def ioctl(self, op, arg):
        if op == 4:
            return self.blocks
        if op == 5:
            return 512
        return 0


def start():
    """Mount the RAM disk. False (and staging off) if that isn't possible."""
    global enabled, _mounted
    if _mounted:
        return True
    if not enabled:
        return False
    try:
        import vfs
        dev = _RAM(BLOCKS)
        vfs.VfsFat.mkfs(dev)
        vfs.mount(vfs.VfsFat(dev), MOUNT)
        _mounted = True
    except Exception as e:  # no vfs, no memory ...
        print("gallery: no RAM disk:", repr(e))
        enabled = False
    return _mounted


def stop():
    global _mounted
    _files.clear()
    if _mounted:
        try:
            import vfs
            vfs.umount(MOUNT)
        except Exception:
            pass
        _mounted = False
    import gc
    gc.collect()


def disable():
    global enabled
    enabled = False
    stop()


def lookup(src):
    """Path of the staged copy of src, or None."""
    return _files.get(src) if _mounted else None


def put(src):
    """Copy src into the RAM disk. True if it is there afterwards."""
    if not _mounted:
        return False
    if src in _files:
        return True
    dst = "%s/%x.jpg" % (MOUNT, hash(src) & 0xFFFFFFF)
    buf = bytearray(2048)
    try:
        with open(src, "rb") as f, open(dst, "wb") as g:
            while True:
                n = f.readinto(buf)
                if not n:
                    break
                g.write(memoryview(buf)[:n])
    except OSError:  # disk full or card trouble: leave it unstaged
        try:
            os.remove(dst)
        except OSError:
            pass
        return False
    _files[src] = dst
    return True


def keep_only(sources):
    """Delete staged copies that aren't in sources."""
    for s in [s for s in _files if s not in sources]:
        try:
            os.remove(_files.pop(s))
        except OSError:
            _files.pop(s, None)
