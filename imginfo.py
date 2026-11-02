"""Image sizes from file headers, so a picture can be checked before it is
decoded. Nothing here decodes pixels."""
import struct

# JPEG start-of-frame markers: they carry the height and width
_SOF = (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF)


def _jpeg(f):
    f.seek(2)
    while True:
        b = f.read(1)
        if not b:
            return None
        if b != b"\xff":
            continue
        m = f.read(1)
        while m == b"\xff":  # fill bytes
            m = f.read(1)
        if not m:
            return None
        m = m[0]
        if m == 0x01 or 0xD0 <= m <= 0xD8 or m == 0:
            continue  # markers with no length, or a stuffed 0xFF00
        if m in (0xD9, 0xDA):
            return None  # end or scan data reached without a frame header
        n = struct.unpack(">H", f.read(2))[0]
        if m in _SOF:
            h, w = struct.unpack(">HH", f.read(5)[1:5])
            return (w, h)
        f.seek(n - 2, 1)


def size(path):
    """(width, height) of a PNG, JPEG, GIF or BMP file, or None if it can't
    be read or isn't one of those."""
    try:
        with open(path, "rb") as f:
            head = f.read(26)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", head[16:24])
            elif head[:6] in (b"GIF87a", b"GIF89a"):
                w, h = struct.unpack("<HH", head[6:10])
            elif head[:2] == b"BM":
                w, h = struct.unpack("<ii", head[18:26])
                h = abs(h)  # a negative height means rows run top to bottom
            elif head[:2] == b"\xff\xd8":
                return _jpeg(f)
            else:
                return None
    except (OSError, struct.error):
        return None
    return (w, h) if w > 0 and h > 0 else None
