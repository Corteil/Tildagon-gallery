"""On-badge self-test for imgtool (the native image library) and the app's
thumbnail code. Run it with:  python3 tools/badge.py test [--photo /sdcard/Pictures/x.jpg]

It makes its own test picture, so it needs no files on the SD card (a real
photo is only used if you ask for one, to time it). Lives in the app folder
while it runs, so the imports are relative."""
import gc, os, sys, time
from . import imgtool

TMP = "/tmp_selftest"
results = []


def check(name, ok, extra=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ((" - " + str(extra)) if extra != "" else ""))


def timed(fn, *a, **k):
    t = time.ticks_ms()
    r = fn(*a, **k)
    return r, time.ticks_diff(time.ticks_ms(), t)


def adler(data):
    a, b = 1, 0
    for c in data:
        a = (a + c) % 65521
        b = (b + a) % 65521
    return (b << 16) | a


def make_png(path, w=200, h=150):
    """A gradient PNG using stored (uncompressed) deflate blocks."""
    import binascii, struct
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw += bytes((x * 255 // w, y * 255 // h, (x + y) * 255 // (w + h)))
    z = bytearray(b"\x78\x01")
    for i in range(0, len(raw), 65535):
        blk = raw[i:i + 65535]
        z += struct.pack("<BHH", 1 if i + 65535 >= len(raw) else 0, len(blk), len(blk) ^ 0xFFFF) + blk
    z += struct.pack(">I", adler(raw))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", binascii.crc32(t + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", bytes(z)) + chunk(b"IEND", b""))


def run(photo=None):
    print("MicroPython", sys.implementation.version, "mpy", sys.implementation._mpy)
    print("platform", sys.platform, "free heap", gc.mem_free())
    try:
        os.mkdir(TMP)
    except OSError:
        pass
    png, jpg, th, th2 = TMP + "/t.png", TMP + "/t.jpg", TMP + "/th.png", TMP + "/th2.png"
    make_png(png)
    check("size(png)", imgtool.size(png) == (200, 150), imgtool.size(png))
    r, ms = timed(imgtool.thumbnail, png, th, 80)
    check("thumbnail png->png", r == (80, 80) and imgtool.size(th) == (80, 80), "%s %d ms" % (r, ms))
    r, ms = timed(imgtool.resize, png, jpg, 100, 85)
    check("resize png->jpg", r == (100, 75) and imgtool.size(jpg) == (100, 75), "%s %d ms" % (r, ms))
    r, ms = timed(imgtool.thumbnail, jpg, th2, 40)
    check("thumbnail jpg->png", r == (40, 40), "%s %d ms" % (r, ms))
    bad = TMP + "/bad.jpg"
    with open(bad, "wb") as f:
        f.write(b"not a picture" * 20)
    try:
        imgtool.size(bad)
        check("bad file rejected", False)
    except ValueError:
        check("bad file rejected", True)
    gc.collect()
    before = gc.mem_free()
    for _ in range(20):
        imgtool.thumbnail(png, th, 80)
    gc.collect()
    after = gc.mem_free()
    check("no leak over 20 thumbnails", before - after < 2048, "%d bytes" % (before - after))
    if photo:
        print("photo", photo, imgtool.size(photo))
        r, ms = timed(imgtool.thumbnail, photo, TMP + "/p_th.png", 80)
        print("  thumbnail %s in %d ms" % (r, ms))
        r, ms = timed(imgtool.resize, photo, TMP + "/p_view.jpg", 480, 85)
        print("  resize    %s in %d ms" % (r, ms))
        check("photo handled", True)
    for f in os.listdir(TMP):
        os.remove(TMP + "/" + f)
    os.rmdir(TMP)
    print("free heap at end", gc.mem_free())
    print("SELFTEST PASSED" if all(results) else "SELFTEST FAILED")
