"""Thumbnails, made by grabbing a region of the screen.

The tile is drawn with ctx.image(), then the same pixels are read back from
display.get_framebuffer() (240x240 RGB565, big-endian) and saved as a PNG that
the browser draws later. Only badge firmware that has get_framebuffer, such as
the build Screengrab needs, can do this: check available() first.

The PNG uses stored (uncompressed) deflate blocks, so there is no compressor
to carry. A 78x78 thumbnail is about 18 KB.
"""
import array
import binascii
import os
import struct

import micropython

try:
    import display
except ImportError:  # not running on a badge
    display = None

FB_W = 240


def available():
    return display is not None and hasattr(display, "get_framebuffer")


@micropython.viper
def _crop(src: ptr8, x0: int, y0: int, w: int, h: int, dst: ptr8):
    # RGB565 region -> PNG scanlines: a filter byte 0, then RGB888 per pixel
    o = 0
    for y in range(h):
        dst[o] = 0
        o += 1
        i = ((y0 + y) * 240 + x0) * 2
        for x in range(w):
            p = (src[i] << 8) | src[i + 1]
            i += 2
            r = (p >> 11) & 31
            g = (p >> 5) & 63
            b = p & 31
            dst[o] = (r << 3) | (r >> 2)
            dst[o + 1] = (g << 2) | (g >> 4)
            dst[o + 2] = (b << 3) | (b >> 2)
            o += 3


@micropython.viper
def _adler(buf: ptr8, n: int, st: ptr32):
    a = 1
    b = 0
    for i in range(n):
        a += buf[i]
        if a >= 65521:
            a -= 65521
        b += a
        if b >= 65521:
            b -= 65521
    st[0] = a
    st[1] = b


def _put(f, data, crc):
    f.write(data)
    return binascii.crc32(data, crc)


def _chunk(f, tag, data):
    f.write(struct.pack(">I", len(data)))
    f.write(tag)
    f.write(data)
    f.write(struct.pack(">I", binascii.crc32(data, binascii.crc32(tag)) & 0xFFFFFFFF))


def _write_png(path, w, h, raw):
    n = len(raw)
    st = array.array("I", (1, 0))
    _adler(raw, n, st)
    adler = struct.pack(">I", (st[1] << 16) | st[0])
    nblk = (n + 65534) // 65535
    mv = memoryview(raw)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        _chunk(f, b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        f.write(struct.pack(">I", 2 + nblk * 5 + n + 4))
        f.write(b"IDAT")
        crc = _put(f, b"\x78\x01", binascii.crc32(b"IDAT"))  # zlib header
        pos = 0
        while pos < n:
            size = min(65535, n - pos)
            last = 1 if pos + size >= n else 0
            crc = _put(f, struct.pack("<BHH", last, size, size ^ 0xFFFF), crc)
            crc = _put(f, mv[pos:pos + size], crc)
            pos += size
        crc = _put(f, adler, crc)
        f.write(struct.pack(">I", crc & 0xFFFFFFFF))
        _chunk(f, b"IEND", b"")
    os.rename(tmp, path)


def _ensure_dir(path):
    d = path.rpartition("/")[0]
    try:
        os.mkdir(d)
    except OSError:
        pass  # already there


def capture(out_path, x, y, w, h):
    """Save the w x h region of the screen whose top-left is pixel (x, y) of
    the 240x240 framebuffer as a PNG at out_path. From ctx coordinates (origin
    in the centre) add 120 to x and y."""
    if w < 1 or h < 1 or x < 0 or y < 0 or x + w > FB_W or y + h > FB_W:
        raise ValueError("region outside the display")
    fb = display.get_framebuffer()
    raw = bytearray(h * (1 + w * 3))
    _crop(fb, x, y, w, h, raw)
    _ensure_dir(out_path)
    _write_png(out_path, w, h, raw)
