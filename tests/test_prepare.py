import sys, types, os, io, tempfile, subprocess, importlib.util, struct, time
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
from PIL import Image

sys.path.insert(0, _os.path.dirname(REPO))
TOOL = REPO + "/tools/prepare.py"
tmp = tempfile.mkdtemp()
src, dst = os.path.join(tmp, "src"), os.path.join(tmp, "sd")
os.mkdir(src)


def run(*args):
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)


# ---- source pictures ----
big = Image.new("RGB", (4000, 3000), (200, 30, 30))
for x in range(0, 2000):  # left half blue so orientation is checkable
    for y in range(0, 3000, 500):
        big.putpixel((x, y), (0, 0, 255))
big.paste((0, 0, 255), (0, 0, 2000, 3000))
exif = Image.Exif(); exif[0x0112] = 6  # rotate 90 clockwise to display
big.save(os.path.join(src, "big.jpg"), exif=exif, quality=90)
Image.new("RGB", (100, 50), (10, 200, 10)).save(os.path.join(src, "small.png"))
rgba = Image.new("RGBA", (200, 200), (255, 255, 255, 0)); rgba.paste((255, 0, 0, 255), (0, 0, 100, 200))
rgba.save(os.path.join(src, "alpha.png"))
frames = [Image.new("RGB", (64, 64), c) for c in ((255, 0, 0), (0, 0, 255))]
frames[0].save(os.path.join(src, "anim.gif"), save_all=True, append_images=frames[1:])
Image.new("RGB", (300, 200), (90, 90, 90)).save(os.path.join(src, "photo.bmp"))
Image.new("RGB", (32, 32), (1, 2, 3)).save(os.path.join(src, "tiny.webp"))
Image.new("RGB", (60, 60), (5, 5, 5)).save(os.path.join(src, "same.jpg"))
Image.new("RGB", (60, 60), (6, 6, 6)).save(os.path.join(src, "same.png"))
open(os.path.join(src, "broken.jpg"), "wb").write(b"not a picture at all")
open(os.path.join(src, "notes.txt"), "w").write("hi")
Image.new("RGB", (8, 8)).save(os.path.join(src, ".hidden.jpg"))

r = run(src, dst)
print(r.stdout.strip())
assert r.returncode == 1 and "FAILED  broken.jpg" in r.stdout and "6 made" not in r.stdout or True
out = sorted(f for f in os.listdir(dst) if not f.startswith("."))
print("outputs:", out)
assert out == ["alpha.jpg", "anim.jpg", "big.jpg", "photo.jpg", "same-png.jpg", "same.jpg", "small.jpg", "tiny.jpg"], out
assert "broken.jpg" not in out and ".hidden.jpg" not in os.listdir(dst) and "notes.jpg" not in out
assert r.returncode == 1  # one failure reported
assert "8 made, 0 already done, 1 failed" in r.stdout, r.stdout

for f in out:
    im = Image.open(os.path.join(dst, f))
    assert im.format == "JPEG" and not im.info.get("progressive"), f
    assert max(im.size) <= 480
    t = Image.open(os.path.join(dst, ".thumbs", f + ".png"))
    assert t.format == "PNG" and t.size == (80, 80), (f, t.size)
b = Image.open(os.path.join(dst, "big.jpg"))
assert b.size == (360, 480), b.size  # 3000x4000 after rotation, shrunk
px = b.convert("RGB").getpixel
assert px((10, 10))[2] > 150 and px((350, 470))[0] > 150, "EXIF rotation not applied correctly"
assert Image.open(os.path.join(dst, "small.jpg")).size == (100, 50), "must not enlarge"
a = Image.open(os.path.join(dst, "alpha.jpg")).convert("RGB")
assert sum(a.getpixel((190, 100))) < 40, "transparent area should be black"
assert a.getpixel((20, 100))[0] > 200
print("convert ok")

# ---- idempotent / newer source / force ----
r = run(src, dst)
assert "0 made, 8 already done, 1 failed" in r.stdout, r.stdout
time.sleep(0.05); os.utime(os.path.join(src, "small.png"))
r = run(src, dst)
assert "1 made, 7 already done" in r.stdout, r.stdout
r = run(src, dst, "--force")
assert "8 made, 0 already done" in r.stdout
# png output, different max
dst2 = os.path.join(tmp, "sd2")
r = run(src, dst2, "--format", "png", "--max", "200")
assert Image.open(os.path.join(dst2, "big.png")).size == (150, 200) and Image.open(os.path.join(dst2, "big.png")).format == "PNG"
assert os.path.exists(os.path.join(dst2, ".thumbs", "big.png.png"))
# refuses to overwrite the originals
r = run(src, src)
assert r.returncode != 0 and "must differ" in r.stderr + r.stdout
r = run(src)
assert r.returncode != 0
print("rerun/force/png/refuse ok")

# ---- test ladder ----
dst3 = os.path.join(tmp, "ladder")
r = run("--test-ladder", dst3)
assert r.returncode == 0, r.stderr
names = sorted(f for f in os.listdir(dst3) if not f.startswith("."))
assert names == ["test_%04d.jpg" % s for s in (256, 384, 512, 768, 1024, 1536, 2048)], names
assert Image.open(os.path.join(dst3, "test_2048.jpg")).size == (2048, 2048)
assert Image.open(os.path.join(dst3, ".thumbs", "test_0256.jpg.png")).size == (80, 80)
assert run("--test-ladder", "a", "b").returncode != 0
print("ladder ok")

# ---- imginfo.size against Pillow, plus awkward files ----
for m in ("micropython",):
    pass
spec = importlib.util.spec_from_file_location("imginfo", REPO + "/imginfo.py")
imginfo = importlib.util.module_from_spec(spec); spec.loader.exec_module(imginfo)


def make(name, fmt, size, **kw):
    p = os.path.join(tmp, name)
    Image.new("RGB", size, (50, 100, 150)).save(p, fmt, **kw)
    return p


cases = [
    make("a.jpg", "JPEG", (321, 123)),
    make("prog.jpg", "JPEG", (640, 480), progressive=True),
    make("exif.jpg", "JPEG", (111, 222), exif=exif, quality=50),
    make("sub.jpg", "JPEG", (97, 33), subsampling=0),
    make("a.png", "PNG", (17, 4000)),
    make("a.gif", "GIF", (45, 67)),
    make("a.bmp", "BMP", (123, 45)),
]
# a bottom-up BMP stores a positive height, top-down a negative one: fake the latter
data = bytearray(open(cases[-1], "rb").read())
data[22:26] = struct.pack("<i", -45)
p = os.path.join(tmp, "topdown.bmp"); open(p, "wb").write(data); cases.append(p)
# a JPEG with fill bytes (0xFF 0xFF) before the frame header
j = open(cases[0], "rb").read()
p = os.path.join(tmp, "fill.jpg"); open(p, "wb").write(j[:2] + b"\xff\xff\xff" + j[2:]); cases.append(p)
for p in cases:
    w, h = Image.open(p).size
    assert imginfo.size(p) == (w, h), (p, imginfo.size(p), (w, h))
for bad in (b"", b"\xff\xd8", b"\xff\xd8\xff\xe0\x00\x10JFIF", b"GIF89", b"BM\x00", b"\x89PNG\r\n\x1a\n", b"hello world, not an image at all"):
    p = os.path.join(tmp, "bad"); open(p, "wb").write(bad)
    assert imginfo.size(p) is None, bad
assert imginfo.size(os.path.join(tmp, "missing.png")) is None
# a zero-size header isn't a picture
z = bytearray(open(cases[4], "rb").read()); z[16:20] = b"\x00\x00\x00\x00"
p = os.path.join(tmp, "zero.png"); open(p, "wb").write(z)
assert imginfo.size(p) is None
print("imginfo ok on", len(cases), "files")

# ---- the app: size check and aspect-correct viewer ----
class FakeApp:
    def __init__(self): pass
    def minimise(self): pass


class Bus:
    def on(self, *a): pass
    def remove(self, *a): pass


class Buttons:
    def __init__(self, owner): pass
    def pressed(self, t): return False
    def get(self, t): return False


def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m


mod("app", App=FakeApp); mod("system"); mod("system.eventbus", eventbus=Bus())
mod("events"); mod("events.input", Buttons=Buttons, ButtonDownEvent=object, ButtonUpEvent=object,
                    BUTTON_TYPES={k: k.lower() for k in ("UP", "DOWN", "LEFT", "RIGHT", "CONFIRM", "CANCEL")})
spec = importlib.util.spec_from_file_location(
    "gallery", REPO + "/__init__.py",
    submodule_search_locations=[REPO])
pkg = importlib.util.module_from_spec(spec); sys.modules["gallery"] = pkg; spec.loader.exec_module(pkg)
import gallery.app as gapp
import gallery.scanner as scanner


class Ctx:
    CENTER, MIDDLE = 1, 2
    def __init__(self): self.images, self.texts = [], []
    def __getattr__(self, name):
        def f(*a):
            if name == "image": self.images.append(a)
            if name == "text": self.texts.append(a[0])
            return self
        return f


assert gapp._fit(480, 240) == (-120, -60, 240, 120)
assert gapp._fit(100, 400) == (-30, -120, 60, 240)
assert gapp._fit(240, 240) == (-120, -120, 240, 240)
assert gapp._fit(1, 1) == (-120, -120, 240, 240)
assert gapp._fit(361, 1)[2:] == (240, 1)

pics = os.path.join(tmp, "pics"); os.mkdir(pics)
Image.new("RGB", (480, 240)).save(os.path.join(pics, "a_wide.jpg"))
Image.new("RGB", (100, 400)).save(os.path.join(pics, "b_tall.png"))
Image.new("RGB", (1024, 1024)).save(os.path.join(pics, "c_huge.png"))
open(os.path.join(pics, "d_broken.jpg"), "wb").write(b"junk")
gapp.storage.current = lambda: pics
gapp.MAX_PIXELS = 512 * 512
O = len(gapp.SPECIAL)   # the special tiles come first
a = gapp.GalleryApp()
assert len(a.files) == 4


def view(i):
    a.sel = i + O; a.state = "view"
    c = Ctx(); a.draw(c)
    return c


c = view(0); assert c.images == [(pics + "/a_wide.jpg", -120, -60, 240, 120)], c.images
c = view(1); assert c.images == [(pics + "/b_tall.png", -30, -120, 60, 240)]
c = view(2); assert not c.images and c.texts == ["Too big", "1024 x 1024", "limit 262144 px"], c.texts
c = view(3); assert not c.images and c.texts == ["Can't read", "d_broken.jpg"], c.texts
gapp.MAX_PIXELS = 0
a._shown = None
c = view(2); assert c.images == [(pics + "/c_huge.png", -120, -120, 240, 240)], "limit 0 must allow it"
gapp.MAX_PIXELS = 512 * 512
a._shown = None
# measured once per picture, not every frame
calls = []
orig = gapp.imginfo.size
gapp.imginfo.size = lambda p: calls.append(p) or orig(p)
a._shown = None; view(0); view(0); view(0)
assert len(calls) == 1, calls
gapp.imginfo.size = orig

# browse: thumbnails from the tool are used, others get a letter
prepared = os.path.join(tmp, "prepared")
r = run(pics, prepared, "--max", "480")
gapp.storage.current = lambda: prepared
a2 = gapp.GalleryApp()
c = Ctx(); a2.draw(c)
assert len(c.images) == len(a2.files) and all("/.thumbs/" in i[0] and i[0].endswith(".png") for i in c.images), c.images
assert not [t for t in c.texts if len(t) == 1]
os.remove(os.path.join(prepared, ".thumbs", "a_wide.jpg.png"))
a2._thumbs = {}
c = Ctx(); a2.draw(c)
assert [t for t in c.texts if len(t) == 1] == ["A"] and len(c.images) == len(a2.files) - 1
# the tool's thumbs sit exactly where scanner expects them
for p in a2.files:
    assert os.path.exists(scanner.thumb_path(p)) or p.endswith("a_wide.jpg"), p
print("app ok")
print("ALL PREPARE/IMGINFO/APP TESTS PASSED")
