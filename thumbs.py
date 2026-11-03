"""Thumbnails and shrunk copies made on the badge by imgtool.py and the native
_imgtool.mpy next to it (see natmod/). If the native part won't load on this
firmware, everything here does nothing and `available` is False: use
tools/prepare.py on a PC instead.

    thumbs.make(path)   makes .thumbs/<name>.png next to the picture
    thumbs.shrunk(path) makes .view240/<name>.jpg and returns its path
"""
import os

try:
    from . import imgtool
except (ImportError, ValueError):  # the native part doesn't fit this firmware
    imgtool = None

available = imgtool is not None
THUMB = 80        # pixels; matches tools/prepare.py
VIEW_MAX = 240    # longest side of a shrunk copy (the screen is 240 x 240)
QUALITY = 85

_failed = set()   # pictures that can't be done (not JPEG/PNG, damaged ...): don't retry


def _dir(path, name):
    d = path.rpartition("/")[0] + "/" + name
    try:
        os.mkdir(d)
    except OSError:
        pass  # already there (or the card is read-only: the write below will say)
    return d


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def failed(path):
    return path in _failed


def make(path):
    """Make the thumbnail for a picture. True if it is there afterwards."""
    from . import scanner
    out = scanner.thumb_path(path)
    if _exists(out):
        return True
    if not available or path in _failed:
        return False
    _dir(path, ".thumbs")
    tmp = out + ".part"
    try:
        imgtool.thumbnail(path, tmp, THUMB)
        os.rename(tmp, out)  # a thumbnail is never seen half-written
    except (ValueError, NotImplementedError, MemoryError, OSError):
        _remove(tmp)
        _failed.add(path)
        return False
    return True


def shrunk(path, build=True):
    """A copy of a picture small enough to draw. Returns its path, or None.
    With build=False only an existing copy is returned."""
    d, _, name = path.rpartition("/")
    out = "%s/.view240/%s.jpg" % (d, name)
    if _exists(out):
        return out
    if not build or not available or path in _failed:
        return None
    _dir(path, ".view240")
    tmp = out + ".part"
    try:
        imgtool.resize(path, tmp, VIEW_MAX, QUALITY)
        os.rename(tmp, out)
    except (ValueError, NotImplementedError, MemoryError, OSError):
        _remove(tmp)
        _failed.add(path)
        return None
    return out
