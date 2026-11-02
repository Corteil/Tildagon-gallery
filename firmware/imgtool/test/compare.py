"""Compare the native module's output with Pillow's. Run: python3 compare.py"""
import os, subprocess, sys, tempfile, time
from PIL import Image, ImageOps, ImageChops, ImageStat
import random

CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imgcli")
tmp = tempfile.mkdtemp()


def photo(w, h, seed=1):
    """Smooth gradients plus blobs and some fine detail: roughly photo-like."""
    random.seed(seed)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (x * 255 // w, y * 255 // h, (x + y) * 255 // (w + h))
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    for _ in range(25):
        x, y = random.randrange(w), random.randrange(h)
        r = random.randrange(max(2, min(w, h) // 20), max(3, min(w, h) // 5))
        d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(random.randrange(256) for _ in range(3)))
    return im


def run(*a):
    t = time.time()
    r = subprocess.run([CLI, *map(str, a)], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), time.time() - t


def err(a, b):
    """mean absolute difference per channel (0..255)"""
    a, b = a.convert("RGB"), b.convert("RGB")
    assert a.size == b.size, (a.size, b.size)
    s = ImageStat.Stat(ImageChops.difference(a, b))
    return sum(s.mean) / 3


def ref_fit(im, n):
    im = im.copy(); im.thumbnail((n, n), Image.BOX); return im


# JPEG-in/JPEG-out adds the encoder's loss (about 2 levels at q90) to the 565 rounding
LIMIT = 6.5
fails = []
def check(name, cond, info=""):
    print(("ok   " if cond else "FAIL ") + name, info)
    if not cond: fails.append(name)

big = photo(1600, 1200)
cases = []

# --- JPEG, several subsamplings ---
for sub in (0, 1, 2):
    p = os.path.join(tmp, "j%d.jpg" % sub); big.save(p, quality=90, subsampling=sub)
    cases.append(("jpeg sub%d" % sub, p))
p = os.path.join(tmp, "prog.jpg"); big.save(p, quality=90, progressive=True); cases.append(("jpeg progressive", p))
p = os.path.join(tmp, "g.jpg"); big.convert("L").save(p); cases.append(("jpeg grey", p))
p = os.path.join(tmp, "odd.jpg"); photo(1003, 777).save(p, quality=90); cases.append(("jpeg odd size", p))
p = os.path.join(tmp, "p.png"); big.save(p); cases.append(("png rgb", p))
p = os.path.join(tmp, "pa.png"); big.convert("RGBA").save(p); cases.append(("png rgba", p))
p = os.path.join(tmp, "pp.png"); big.convert("P", palette=Image.ADAPTIVE).save(p); cases.append(("png palette", p))
p = os.path.join(tmp, "pg.png"); big.convert("L").save(p); cases.append(("png grey", p))

for name, p in cases:
    src = Image.open(p).convert("RGB")
    # fit -> JPEG
    out = os.path.join(tmp, "fit.jpg")
    rc, text, dt = run("fit", 480, p, out, 90)
    ok = rc == 0
    if ok:
        got = Image.open(out); ref = ref_fit(src, 480)
        e = err(got, ref) if got.size == ref.size else 99
        check(name + " fit 480", got.format == "JPEG" and got.size == ref.size and e < LIMIT, "%s err=%.2f %.3fs" % (got.size, e, dt))
    else:
        check(name + " fit 480", False, text)
    # thumb -> PNG
    out = os.path.join(tmp, "t.png")
    rc, text, dt = run("thumb", 80, p, out)
    if rc == 0:
        got = Image.open(out); got.load()
        ref = ImageOps.fit(src, (80, 80), Image.BOX)
        e = err(got, ref)
        check(name + " thumb 80", got.format == "PNG" and got.size == (80, 80) and e < LIMIT, "err=%.2f %.3fs" % (e, dt))
    else:
        check(name + " thumb 80", False, text)

# --- EXIF orientation 1..8 ---
base = Image.new("RGB", (300, 200), (0, 0, 0))
for x in range(150): 
    for y in range(100): base.putpixel((x, y), (255, 0, 0))          # red top-left
for x in range(150, 300):
    for y in range(100, 200): base.putpixel((x, y), (0, 0, 255))     # blue bottom-right
for o in range(1, 9):
    p = os.path.join(tmp, "o%d.jpg" % o)
    ex = Image.Exif(); ex[0x0112] = o
    base.save(p, quality=95, subsampling=0, exif=ex)
    out = os.path.join(tmp, "o_out.jpg")
    rc, text, _ = run("fit", 300, p, out, 95)
    ref = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
    if rc != 0:
        check("orientation %d" % o, False, text); continue
    got = Image.open(out).convert("RGB")
    check("orientation %d" % o, got.size == ref.size and err(got, ref) < 3.0, "%s vs %s err=%.2f" % (got.size, ref.size, err(got, ref) if got.size == ref.size else -1))
    # square thumbs follow orientation too
    t = os.path.join(tmp, "o_t.png")
    rc, text, _ = run("thumb", 64, p, t)
    refs = ImageOps.fit(ref, (64, 64), Image.BOX)
    check("orientation %d thumb" % o, rc == 0 and err(Image.open(t), refs) < LIMIT)

# --- never enlarges; tiny pictures ---
p = os.path.join(tmp, "small.jpg"); photo(60, 40).save(p, quality=95)
out = os.path.join(tmp, "s.jpg"); rc, text, _ = run("fit", 480, p, out)
check("small picture is not enlarged", rc == 0 and Image.open(out).size == (60, 40), text)
rc, text, _ = run("thumb", 80, p, out)
check("small thumb is not enlarged", rc == 0, text)
p = os.path.join(tmp, "one.png"); Image.new("RGB", (1, 1), (9, 9, 9)).save(p)
rc, text, _ = run("fit", 480, p, out); check("1x1 png", rc == 0, text)

# --- bad input must fail cleanly ---
for name, data in (("empty", b""), ("junk", b"x" * 500), ("truncated jpeg", open(os.path.join(tmp, "j1.jpg"), "rb").read()[:3000]),
                   ("truncated png", open(os.path.join(tmp, "p.png"), "rb").read()[:3000]),
                   ("jpeg header only", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00")):
    p = os.path.join(tmp, "bad"); open(p, "wb").write(data)
    rc, text, _ = run("fit", 480, p, os.path.join(tmp, "bad.out"))
    check("bad: " + name, rc == 1 and text.startswith("rc=-"), text)

# --- unsupported: interlaced PNG, 16-bit PNG (made with ImageMagick) ---
src_png = os.path.join(tmp, "p.png")
for name, args in (("interlaced", ["-interlace", "PNG"]), ("16-bit", ["-depth", "16"])):
    p = os.path.join(tmp, name + ".png")
    subprocess.run(["convert", src_png, "-resize", "200x150", *args, p], check=True)
    rc, text, _ = run("fit", 100, p, os.path.join(tmp, "x.jpg"))
    check(name + " png reported unsupported", rc == 1 and "rc=-2" in text, text)

# --- info ---
for name, p in cases[:4] + cases[5:7]:
    rc, text, _ = run("info", 0, p, "-")
    w, h = Image.open(p).size
    check("info " + name, text == "rc=0 %d %d" % (w, h), text)

# --- speed (host, informational) ---
huge = os.path.join(tmp, "huge.jpg"); photo(4000, 3000, 7).save(huge, quality=90)
rc, text, dt = run("fit", 480, huge, os.path.join(tmp, "h.jpg"), 85)
print("12 MP JPEG -> 480 on this PC: %.3fs  %s" % (dt, text))
rc, text, dt = run("thumb", 80, huge, os.path.join(tmp, "h.png"))
print("12 MP JPEG -> 80 thumb on this PC: %.3fs  %s" % (dt, text))
hp = os.path.join(tmp, "huge.png"); photo(2000, 1500, 3).save(hp)
rc, text, dt = run("fit", 480, hp, os.path.join(tmp, "hp.jpg"), 85)
print("3 MP PNG -> 480 on this PC: %.3fs  %s" % (dt, text))

print("\n%d failed" % len(fails), fails)
sys.exit(1 if fails else 0)
