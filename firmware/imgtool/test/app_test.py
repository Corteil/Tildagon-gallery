"""The gallery app with the native module present. imgtool is stood in for by
the host imgcli build (same C++ core), so the app's thumbnail and
shrink-on-view logic runs end to end. Run: python3 app_test.py"""
import importlib.util, os, subprocess, sys, tempfile, types
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CLI = os.path.join(HERE, "imgcli")


class ImgToolStandIn(types.ModuleType):
    calls = []

    def _run(self, mode, size, src, dst, q=85):
        self.calls.append((mode, os.path.basename(src)))
        if not os.path.exists(src):
            raise OSError(2)
        r = subprocess.run([CLI, mode, str(size), src, dst, str(q)], capture_output=True, text=True)
        if r.returncode:
            code = int(r.stdout.split("=")[1])
            raise NotImplementedError if code == -2 else ValueError("bad")

    def thumbnail(self, src, dst, size=80): self._run("thumb", size, src, dst)
    def resize(self, src, dst, max=480, quality=85): self._run("fit", max, src, dst, quality)


imgtool = ImgToolStandIn("imgtool")
sys.modules["imgtool"] = imgtool


def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m


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

mod("app", App=FakeApp); mod("system"); mod("system.eventbus", eventbus=Bus())
mod("events"); mod("events.input", Buttons=Buttons, ButtonDownEvent=object, ButtonUpEvent=object,
                    BUTTON_TYPES={k: k.lower() for k in ("UP", "DOWN", "LEFT", "RIGHT", "CONFIRM", "CANCEL")})
spec = importlib.util.spec_from_file_location("gallery", REPO + "/__init__.py", submodule_search_locations=[REPO])
pkg = importlib.util.module_from_spec(spec); sys.modules["gallery"] = pkg; spec.loader.exec_module(pkg)
import gallery.app as gapp
import gallery.thumbs as thumbs
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


assert thumbs.available
tmp = tempfile.mkdtemp()
pics = os.path.join(tmp, "pics"); os.mkdir(pics)
Image.new("RGB", (1600, 1200), (200, 50, 50)).save(pics + "/a_big.jpg")
Image.new("RGB", (300, 200), (50, 200, 50)).save(pics + "/b_small.png")
Image.new("RGB", (40, 40), (50, 50, 200)).save(pics + "/c_anim.gif")        # imgtool can't read GIF
open(pics + "/d_bad.jpg", "wb").write(b"junk")
Image.new("RGB", (800, 800), (9, 9, 9)).save(pics + "/e_square.png")
gapp.ROOT = pics
a = gapp.GalleryApp()
assert len(a.files) == 5

# --- browse: thumbnails appear one per frame, selected tile first ---
a.sel = 1
c = Ctx(); a.draw(c); a.update(30)           # first frame loads the page, update makes one thumb
assert thumbs.imgtool.calls[-1] == ("thumb", "b_small.png"), thumbs.imgtool.calls
assert os.path.exists(pics + "/.thumbs/b_small.png.png")
for _ in range(10):
    c = Ctx(); a.draw(c); a.update(30)
t = sorted(f for f in os.listdir(pics + "/.thumbs"))
assert t == ["a_big.jpg.png", "b_small.png.png", "e_square.png.png"], t   # gif and junk skipped
assert not any(f.endswith(".part") for f in t)
for f in t:
    im = Image.open(pics + "/.thumbs/" + f); assert im.size == (80, 80) and im.format == "PNG"
n = len(thumbs.imgtool.calls)
for _ in range(5):
    c = Ctx(); a.draw(c); a.update(30)
assert len(thumbs.imgtool.calls) == n, "failed/finished pictures must not be retried every frame"
c = Ctx(); a.draw(c)
assert len(c.images) == 3 and c.texts == ["C", "D"], (len(c.images), c.texts)
print("thumbnails ok")

# --- view: a too-big picture is shrunk, then drawn from the copy ---
a.sel = 0; a.state = "view"
c = Ctx(); a.draw(c)
assert c.texts == ["Resizing..."] and not c.images, (c.texts, c.images)
a.update(30)
c = Ctx(); a.draw(c)
assert not c.texts and len(c.images) == 1, c.texts
assert c.images[0][0] == pics + "/.view/a_big.jpg.jpg" and c.images[0][3:] == (240, 180), c.images
v = Image.open(pics + "/.view/a_big.jpg.jpg"); assert v.size == (480, 360) and v.format == "JPEG"
# coming back later uses the copy straight away, no flash of "Resizing"
a.sel = 1; a.draw(Ctx()); a.sel = 0
before = len(thumbs.imgtool.calls)
c = Ctx(); a.draw(c); assert c.images and not c.texts and len(thumbs.imgtool.calls) == before
# moving on while it was "Resizing" must not apply one picture's copy to another
Image.new("RGB", (1500, 1500), (1, 2, 3)).save(pics + "/f_big2.png")
a.files = scanner.list_images(pics); a.sel = a.files.index(pics + "/f_big2.png"); a.state = "view"; a._shown = None
c = Ctx(); a.draw(c); assert c.texts == ["Resizing..."]
a.update(30)                                # shrinks f_big2 ...
a.sel = 0                                   # ... but the user has already moved on
c = Ctx(); a.draw(c)
assert c.images and c.images[0][0] == pics + "/.view/a_big.jpg.jpg", c.images
a.sel = a.files.index(pics + "/f_big2.png")
c = Ctx(); a.draw(c); assert c.images[0][0] == pics + "/.view/f_big2.png.jpg", c.images
print("shrink on view ok")

# --- view: a big picture imgtool can't read says so ---
Image.new("RGB", (1024, 1024)).save(pics + "/g_big.gif")
a.files = scanner.list_images(pics); a.sel = a.files.index(pics + "/g_big.gif"); a.state = "view"
c = Ctx(); a.draw(c); assert c.texts == ["Resizing..."]
a.update(30); c = Ctx(); a.draw(c)
assert c.texts == ["Too big", "1024 x 1024", "limit 262144 px"], c.texts
n = len(thumbs.imgtool.calls); a.update(30); a.draw(Ctx()); assert len(thumbs.imgtool.calls) == n
print("unreadable big picture ok")

# --- stale cache: a newer original is shrunk again ---
os.utime(pics + "/a_big.jpg", None)
os.utime(pics + "/.view/a_big.jpg.jpg", (1, 1))
assert thumbs.shrunk(pics + "/a_big.jpg", build=False) is None
assert thumbs.shrunk(pics + "/a_big.jpg") == pics + "/.view/a_big.jpg.jpg"
print("stale copy ok")

# --- no imgtool: the app behaves as before ---
thumbs.available = False
b = gapp.GalleryApp(); b.sel = 0; b.state = "view"
c = Ctx(); b.draw(c); assert c.texts == ["Too big", "1600 x 1200", "limit 262144 px"], c.texts
b.update(30)
print("ALL NATIVE-APP TESTS PASSED")
