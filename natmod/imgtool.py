"""imgtool: shrink JPEG and PNG pictures and make thumbnails, fast.

A small MicroPython library: this file plus _imgtool.mpy, a native module that
does the pixel work (JPEGDEC, PNGdec and JPEGENC by Larry Bank). Copy both to
/lib on the badge; no firmware change is needed.

    import imgtool
    imgtool.size("/sdcard/Pictures/a.jpg")                   # (4000, 3000)
    imgtool.thumbnail("a.jpg", "a.png", 80)                  # centre-cropped square PNG
    imgtool.resize("a.jpg", "a_small.jpg", 480, quality=85)  # longest side 480, JPEG

All three return the size of what they wrote (size() the size of the picture).

Raises ValueError (not a readable JPEG or PNG), NotImplementedError (interlaced
or 16-bit PNG, some rare JPEGs), MemoryError, or OSError (file trouble).
"""
import os

import _imgtool

_THUMB_PNG = 0
_FIT_JPEG = 1
_CHUNK = 4096  # bytes read from the file at a time


def _make(src, mode, n, quality):
    with open(src, "rb") as f:
        return _imgtool.make(f.readinto, f.seek, os.stat(src)[6], bytearray(_CHUNK), mode, n, quality)


def size(path):
    """(width, height) of a JPEG or PNG, read from its header."""
    with open(path, "rb") as f:
        return _imgtool.info(f.readinto, f.seek, os.stat(path)[6], bytearray(_CHUNK))


def thumbnail(src, dst, size=80):
    """Write a size x size PNG thumbnail of src to dst, cropped to a square
    from the middle. A picture smaller than that keeps its size."""
    data, w, h, _, _ = _make(src, _THUMB_PNG, size, 0)
    with open(dst, "wb") as f:
        f.write(data)
    return (w, h)


def resize(src, dst, max=480, quality=85):
    """Write a JPEG of src to dst, shrunk to fit max x max (never enlarged) and
    turned upright using its EXIF rotation. quality is 1-100."""
    data, w, h, _, _ = _make(src, _FIT_JPEG, max, quality)
    with open(dst, "wb") as f:
        f.write(data)
    return (w, h)
