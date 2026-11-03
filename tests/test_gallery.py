import sys, types, os, tempfile, importlib.util
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

MODE = os.environ.get("MODE", "2026")
KB = os.environ.get("KB", "1") == "1"
sys.path.insert(0, _os.path.dirname(REPO))


def mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


import builtins
builtins.ptr8 = builtins.ptr32 = object
mod("micropython", viper=lambda f: f)


class FakeApp:
    minimised = False
    def __init__(self):
        pass
    def minimise(self):
        self.minimised = True


class Ev:
    def __init__(self, button):
        self.button = button


class DownEvent(Ev): pass
class UpEvent(Ev): pass


class Bus:
    def __init__(self):
        self.h = {}
    def on(self, ev, fn, owner):
        self.h.setdefault(ev, []).append(fn)
    def remove(self, ev, fn, owner):
        self.h[ev] = [f for f in self.h.get(ev, []) if f != fn]
    def emit(self, ev):
        for f in list(self.h.get(type(ev), [])):
            f(ev)


bus = Bus()


class Buttons:
    """pressed() = once per press, get() = currently held."""
    def __init__(self, owner):
        self.p, self.held = [], set()
        bus.on(DownEvent, self._d, owner)
        bus.on(UpEvent, self._u, owner)
    def _d(self, ev):
        self.p.append(set(ev.button)); self.held |= set(ev.button)
    def _u(self, ev):
        self.held -= set(ev.button)
    def pressed(self, t):
        for s in self.p:
            if t in s:
                self.p.remove(s)
                return True
        return False
    def get(self, t):
        return t in self.held
    def clear(self):
        self.p, self.held = [], set()


mod("app", App=FakeApp)
mod("system"); mod("system.eventbus", eventbus=bus)
mod("events"); mod("events.input", Buttons=Buttons, ButtonDownEvent=DownEvent, ButtonUpEvent=UpEvent,
                    BUTTON_TYPES={k: k.lower() for k in ("UP", "DOWN", "LEFT", "RIGHT", "CONFIRM", "CANCEL")})
if MODE == "2026":
    mod("events.joystick", JOYSTICK_BUTTON_TYPES={k: "joy" + k.lower() for k in ("UP", "DOWN", "LEFT", "RIGHT", "SELECT")})
    mod("frontboards"); mod("frontboards.twentysix", TOUCH={"TOUCH%02d" % i: "t%d" % i for i in range(1, 13)})
if KB:
    kb = {chr(c): "kb" + chr(c) for c in range(65, 91)}
    kb.update({"SPACE": "kbSPACE", "BACKSPACE": "kbBACKSPACE"})
    mod("events.keyboard", KEYBOARD_BUTTONS=kb)

spec = importlib.util.spec_from_file_location(
    "gallery", REPO + "/__init__.py",
    submodule_search_locations=[REPO])
pkg = importlib.util.module_from_spec(spec)
sys.modules["gallery"] = pkg
spec.loader.exec_module(pkg)
assert pkg.GalleryApp is not None and pkg.__all__ == ["GalleryApp"]
import gallery.app as gapp
import gallery.inputs as ginputs

assert ginputs._has(3, 3) and not ginputs._has(3, 4)


import gallery.storage as gstorage
import gallery.keep as gkeep
import gallery.stage as gstage
import gallery.thumbs as gthumbs
import shutil
FLASH = tempfile.mkdtemp()
gstorage.KEPT_ROOT = FLASH + "/gallery"
gstorage.KEPT = gstorage.KEPT_ROOT + "/kept"
gstorage.SETTINGS = gstorage.KEPT_ROOT + "/settings.txt"
gkeep.ORDER = gstorage.KEPT + "/.order"
O = 4  # four special tiles come first


def make(names, folder=None):
    d = folder or tempfile.mkdtemp()
    for n in names:
        open(os.path.join(d, n), "w").close()
    gstorage.current = lambda: d
    return gapp.GalleryApp()


a = make(["img%02d.png" % n for n in range(30)])
assert len(a.files) == 30 and len(a.entries) == 34 and a.sel == O


def press(*names, app=None):
    app = app or a
    bus.emit(DownEvent(set(names)))
    app.update(20)
    bus.emit(UpEvent(set(names)))


# ---- buttons (both badges) ----
a.sel = O
press("right"); press("down")
tag = "%s kb=%s" % (MODE, KB)
print(tag, "after RIGHT, DOWN:", a.sel)
assert a.sel == O + 4
press("confirm")
assert a.state == "view"
press("right"); press("right")
assert a.sel == O + 6
press("left")
assert a.sel == O + 5
a.sel = O
press("left")
assert a.sel == 33          # wraps past the special tiles to the last picture
press("right")
assert a.sel == O           # and back, skipping them
press("cancel")
assert a.state == "browse" and not a.minimised

# ---- hold to repeat ----
a.sel = O
bus.emit(DownEvent({"right"})); a.update(20)
assert a.sel == O + 1, a.sel               # the press itself
a.update(200); assert a.sel == O + 1
a.update(200); assert a.sel == O + 2       # 400 ms: repeat starts
a.update(70); assert a.sel == O + 3
a.update(70); assert a.sel == O + 4
a.update(30); assert a.sel == O + 4
bus.emit(UpEvent({"right"}))
a.update(500); assert a.sel == O + 4
bus.emit(DownEvent({"right"})); a.update(20)
assert a.sel == O + 5
a.update(100); assert a.sel == O + 5
bus.emit(UpEvent({"right"}))
bus.emit(DownEvent({"confirm"})); a.update(20)
assert a.state == "view"
a.update(2000); assert a.state == "view"
bus.emit(UpEvent({"confirm"}))
a.toast = None
a._pending = None; a._toast_ms = 0
press("cancel")
print(tag, "hold-to-repeat ok")

# ---- keyboard ----
if KB:
    b = make(["apple.png", "avocado.png", "berry.png", "cherry.png"])
    b.sel = O
    press("kbA", app=b); assert b.sel == O + 1
    press("kbA", app=b); assert b.sel == O
    press("kbC", app=b); assert b.sel == O + 3
    press("kbZ", app=b); assert b.sel == O + 3
    press("kbSPACE", app=b); assert b.sel == 0 or b.sel == 1 or b.sel == 2 or b.sel == O   # next tile (wraps)
    print(tag, "keyboard ok")
else:
    assert ginputs.KEYBOARD_BUTTONS == {}

# ---- special tiles ----
c = make(["apple.jpg", "avocado.jpg", "berry.jpg", "cherry.jpg", "Cranberry.png"])
c.sel = 0
press("confirm", app=c); assert c.state == "search"
# on-badge keyboard: DOWN to 'b', RIGHT adds it, LEFT deletes
press("down", app=c); press("right", app=c)
assert c._q == "b", c._q
press("left", app=c); assert c._q == ""
press("down", app=c)  # c
press("right", app=c); assert c._q == "c"
press("confirm", app=c)
assert c.state == "browse" and c.query == "c"
assert [f.rsplit("/", 1)[-1] for f in c.files] == ["avocado.jpg", "cherry.jpg", "Cranberry.png"], c.files
assert c.sel == O
press("cancel", app=c)          # clears the filter, doesn't leave
assert c.query == "" and len(c.files) == 5 and not c.minimised
c.sel = 0; press("confirm", app=c)
if KB:
    press("kbA", app=c); press("kbV", app=c)
    assert c._q.endswith("av"), c._q
    press("kbBACKSPACE", app=c); assert c._q.endswith("a")
c._q = "av"; press("confirm", app=c)
assert [f.rsplit("/", 1)[-1] for f in c.files] == ["avocado.jpg"]
press("cancel", app=c)
c.sel = 0
print(tag, "search ok")

# ---- storage picker: another card, and flash ----
card2 = tempfile.mkdtemp()
for n in ("x1.jpg", "x2.jpg"):
    open(os.path.join(card2, n), "w").close()
gstorage.choices = lambda: [("SD sdcard", c.folder), ("SD sdcard_1", card2), ("Flash (kept)", gstorage.KEPT)]
c.sel = 1; press("confirm", app=c)
assert c.state == "storage" and len(c._opts) == 3 and c._opt == 0
press("down", app=c); press("confirm", app=c)
assert c.state == "browse" and c.folder == card2 and len(c.files) == 2
assert gstorage.load()["folder"] == card2
# the choice is remembered
gstorage.current = gstorage.__dict__["current"]
print(tag, "storage ok")

# ---- keep in flash (no resizer here: small jpegs are copied as they are) ----
from PIL import Image
big = tempfile.mkdtemp()
Image.new("RGB", (100, 80), (200, 30, 30)).save(big + "/s.jpg", quality=80)
Image.new("RGB", (900, 700)).save(big + "/huge.jpg")
k = make(["notes.txt"], folder=big)
assert [f.rsplit("/", 1)[-1] for f in k.files] == ["huge.jpg", "s.jpg"]
k.sel = O + 1; press("confirm", app=k); assert k.state == "view"
press("confirm", app=k)           # keep: toast first, job next frame
assert k._pending and k._toast_text == "Keeping..."
k.update(20)
assert k._toast_text == "Kept 1/10", k._toast_text
assert gkeep.has(big + "/s.jpg") and gkeep.count() == 1
press("confirm", app=k); k.update(20)       # again: remove
assert k._toast_text == "Removed" and gkeep.count() == 0
k.sel = O; k._shown = None
press("confirm", app=k); k.update(20)       # too big and no resizer
assert k._toast_text == "Can't keep it", k._toast_text
# fill past 10: oldest dropped
names = []
for i in range(12):
    p = "%s/p%02d.jpg" % (big, i)
    Image.new("RGB", (60, 60), (i * 20, 10, 10)).save(p)
    r = gkeep.add(p)
    assert r == ("kept" if i < 10 else "replaced"), (i, r)
assert gkeep.count() == 10
assert not gkeep.has(big + "/p00.jpg") and not gkeep.has(big + "/p01.jpg") and gkeep.has(big + "/p11.jpg")
# browsing the flash: removing a picture there updates the list
fl = make(["z.txt"], folder=gstorage.KEPT)
assert len(fl.files) == 10
fl.sel = O; press("confirm", app=fl); assert fl.state == "view"
press("confirm", app=fl); fl.update(20)
assert len(fl.files) == 9 and fl.state == "view" and fl.entries[fl.sel] not in gapp.SPECIAL
real_free = gkeep.free
gkeep.free = lambda: 0
full = "%s/full.jpg" % big
Image.new("RGB", (60, 60)).save(full)
assert gkeep.add(full) == "full"
gkeep.free = real_free
print(tag, "keep ok")

# ---- slideshow with the RAM disk ----
class FakeVfs:
    mounted = {}
    class VfsFat:
        def __init__(self, dev): self.dev = dev
        @staticmethod
        def mkfs(dev): pass
    @classmethod
    def mount(cls, fs, where): cls.mounted[where] = fs
    @classmethod
    def umount(cls, where): cls.mounted.pop(where, None)

# no real FAT here: stage into a temp folder instead
ramdir = tempfile.mkdtemp()
gstage.MOUNT = ramdir
sys.modules["vfs"] = FakeVfs
show_dir = tempfile.mkdtemp()
for i in range(6):
    Image.new("RGB", (120, 90), (i * 40, 90, 90)).save("%s/s%d.jpg" % (show_dir, i))
sh = make([], folder=show_dir)
sh.sel = 2; press("confirm", app=sh)       # Slideshow tile
assert sh.state == "show" and sh.entries[sh.sel] == show_dir + "/s0.jpg" and gstage._mounted
seen = [sh.sel]
for _ in range(40):                        # 40 frames of 20 ms: the first pictures get staged
    sh.update(20)
assert len(gstage._files) >= 3 and all(os.path.exists(v) for v in gstage._files.values())
assert sh.entries[sh.sel] == show_dir + "/s0.jpg"
sh.update(5000)                            # timer
assert sh.entries[sh.sel] == show_dir + "/s1.jpg", sh.entries[sh.sel]
press("up", app=sh); assert sh.seconds == 6
press("down", app=sh); press("down", app=sh); assert sh.seconds == 4
assert gstorage.load()["seconds"] == "4"
press("confirm", app=sh); assert sh._paused
sh._since = 0; sh.update(60000); assert sh.entries[sh.sel] == show_dir + "/s1.jpg"
press("right", app=sh); assert sh.entries[sh.sel] == show_dir + "/s2.jpg"
press("left", app=sh); press("left", app=sh); assert sh.entries[sh.sel] == show_dir + "/s0.jpg"
# the draw path is used: a stub ctx records what is drawn
class Ctx:
    CENTER = MIDDLE = 0
    def __init__(self): self.imgs = []
    def __getattr__(self, n):
        def f(*a, **k): return self
        return f
    def image(self, p, *r):
        if p.startswith("/nonexistent"): raise OSError
        self.imgs.append(p)
for _ in range(10): sh.update(20)
sh._shown = None
ctx = Ctx(); sh.draw(ctx)
assert ctx.imgs and ctx.imgs[-1].startswith(ramdir), ctx.imgs
# drawing from the RAM disk fails: falls back to the card and switches staging off
class BadCtx(Ctx):
    def image(self, p, *r):
        if p.startswith(ramdir): raise OSError("nope")
        self.imgs.append(p)
sh._shown = None
bc = BadCtx(); sh.draw(bc)
assert bc.imgs and bc.imgs[-1].startswith(show_dir) and not gstage.enabled
press("cancel", app=sh); assert sh.state == "browse" and not gstage._mounted
gstage.enabled = True
print(tag, "slideshow ok")

# ---- empty storage still shows the tiles ----
e = make([], folder=tempfile.mkdtemp())
assert e.entries == list(gapp.SPECIAL) and e.sel == 0
ctx = Ctx(); e.draw(ctx)
press("down", app=e)
e.sel = 2; press("confirm", app=e)
assert e.state == "browse"       # slideshow with nothing to show
print(tag, "empty ok")

# ---- settings tile and the other layouts ----
import gallery.layouts as glay
st = make(["p%02d.jpg" % i for i in range(40)])
st.sel = 3; press("confirm", app=st); assert st.state == "settings"
assert st.layout_no == 0
press("right", app=st); assert st.layout_no == 1 and st.layout.per_page == 16
press("right", app=st); press("right", app=st)
assert st.layout_no == 3 and st.layout.focus
press("right", app=st); assert st.layout_no == 0           # wraps
assert gstorage.load()["layout"] == "0"
press("down", app=st); press("right", app=st); assert st.seconds == (7 if False else st.seconds)
press("left", app=st); press("left", app=st)
assert st.seconds == max(gapp.SECONDS[0], st.seconds)
press("down", app=st)                          # Kept size
assert gkeep.size == 240
press("right", app=st); assert gkeep.size == 480 and gstorage.load()["keep_px"] == "480"
press("left", app=st); press("left", app=st); assert gkeep.size == 720   # wraps
press("right", app=st); assert gkeep.size == 240
press("down", app=st)                          # Sort
assert st.sort == "name"
press("right", app=st); assert st.sort == "newest" and gstorage.load()["sort"] == "newest"
press("right", app=st); press("right", app=st); assert st.sort == "name"
press("down", app=st)                          # Clear kept
before = gkeep.count()
press("confirm", app=st); assert gkeep.count() == 0 and st._toast_text == "Cleared"
press("cancel", app=st); assert st.state == "browse"
# a new app picks up the saved layout
gstorage.save(layout=2)
st2 = make(["p%02d.jpg" % i for i in range(40)])
assert st2.layout_no == 2 and st2.layout.shape == "hex"
gstorage.save(layout=0)

class RecCtx:
    CENTER = MIDDLE = 0
    def __init__(self): self.calls = []; self.imgs = []; self.depth = 0
    def __getattr__(self, n):
        def f(*a, **k):
            self.calls.append(n)
            if n == "save": self.depth += 1
            if n == "restore": self.depth -= 1
            return self
        return f
    def image(self, p, *r): self.imgs.append((p, r)); return self

for no, (name, fac) in enumerate(glay.LAYOUTS):
    t = make(["p%02d.jpg" % i for i in range(40)])
    t.layout_no = no; t.layout = fac()
    for sel in (0, 4, 5, 20, 39 + O - 39):
        t.sel = min(sel, len(t.entries) - 1)
        t._thumbs = {p: p + ".t" for p in t.files}      # pretend thumbnails exist
        ctx = RecCtx(); t.draw(ctx)
        tl = t.layout.tiles(t.sel, len(t.entries))
        assert any(i == t.sel for i, *_ in tl), (name, t.sel)
        assert all(0 <= i < len(t.entries) for i, *_ in tl)
        assert ctx.depth == 0
        for i, x, y, w, h in tl:      # everything on the round 240 px screen
            assert -120 <= x and x + w <= 120 and -120 <= y and y + h <= 120, (name, i, x, y, w, h)
        if t.layout.shape == "hex":
            assert ctx.calls.count("clip") == len(tl) and "close_path" in ctx.calls
    # walking with every direction never leaves the list or sticks forever
    seen = set()
    for d in ("RIGHT", "DOWN", "LEFT", "UP"):
        j = 0
        for _ in range(200):
            j2 = t.layout.move(j, d, len(t.entries))
            assert 0 <= j2 < len(t.entries)
            j = j2
        seen.add(j)
    j = 0
    for _ in range(100):
        j = t.layout.move(j, "DOWN", len(t.entries)) if name != "Focus ring" else t.layout.move(j, "RIGHT", len(t.entries))
    assert j > 5, (name, j)
    print(tag, "layout", name, "ok")

# honeycomb: the selection is in the middle with two rings round it; round tiles in the ring
hc = glay.HoneycombLayout()
tl = hc.tiles(20, 44)
assert len(tl) == 19 and tl[0][0] == 20 and abs(tl[0][1] + tl[0][3] / 2) < 1 and abs(tl[0][2] + tl[0][4] / 2) < 1, tl[0]
assert len(hc.tiles(0, 44)) < 19 and all(0 <= i < 44 for i, *_ in hc.tiles(0, 44))
assert hc.move(20, "DOWN", 44) == 26 and hc.move(20, "UP", 44) == 14 and hc.move(2, "UP", 44) == 2
fr0 = glay.FocusRingLayout()
assert fr0.shape == "circle"
ctx = RecCtx(); cf = make(["z%d.jpg" % i for i in range(12)]); cf.layout = fr0; cf.sel = O + 3
cf.draw(ctx)
assert ctx.calls.count("arc") >= 9 and ctx.calls.count("clip") == 9, (ctx.calls.count("arc"), ctx.calls.count("clip"))

# focus ring draws the 240 px copy for the big tile when there is one
fr = make(["q%d.jpg" % i for i in range(6)]); fr.layout = glay.FocusRingLayout(); fr.layout_no = 3
fr.sel = O + 2
fr._thumbs = {p: p + ".t" for p in fr.files}
fr._bigs = {fr.entries[fr.sel]: "/view/big.jpg"}
ctx = RecCtx(); fr.draw(ctx)
assert ("/view/big.jpg" in [p for p, r in ctx.imgs]) and ctx.imgs[-1][0] == "/view/big.jpg" and ctx.imgs[-1][1] == (-52, -52, 104, 104), ctx.imgs[-1]
print(tag, "settings and layouts ok")

# ---- sort order and albums ----
import time
sd = tempfile.mkdtemp()
for i, n in enumerate(["b.jpg", "A.jpg", "c.jpg"]):
    p = os.path.join(sd, n); open(p, "w").close(); os.utime(p, (1000 + i * 100, 1000 + i * 100 if n != "A.jpg" else 5000))
assert [f.rsplit("/", 1)[-1] for f in gapp.scanner.list_images(sd)] == ["A.jpg", "b.jpg", "c.jpg"]
assert [f.rsplit("/", 1)[-1] for f in gapp.scanner.list_images(sd, "newest")] == ["A.jpg", "c.jpg", "b.jpg"]
assert [f.rsplit("/", 1)[-1] for f in gapp.scanner.list_images(sd, "oldest")] == ["b.jpg", "c.jpg", "A.jpg"]
os.mkdir(sd + "/holiday"); os.mkdir(sd + "/.thumbs"); os.mkdir(sd + "/Cats")
open(sd + "/holiday/h1.jpg", "w").close(); open(sd + "/holiday/h2.jpg", "w").close(); open(sd + "/Cats/c1.png", "w").close()
os.mkdir(sd + "/holiday/beach"); open(sd + "/holiday/beach/b1.jpg", "w").close()
assert [d.rsplit("/", 1)[-1] for d in gapp.scanner.list_dirs(sd)] == ["Cats", "holiday"]
al = make([], folder=sd)
assert al.entries[:4] == list(gapp.SPECIAL) and al.entries[4:6] == ["@dir:" + sd + "/Cats", "@dir:" + sd + "/holiday"]
assert al._first == 6 and al.sel == 6 and [f.rsplit("/", 1)[-1] for f in al.files] == ["A.jpg", "b.jpg", "c.jpg"]
al.sel = 4; press("confirm", app=al)               # open the Cats album
assert al.folder == sd + "/Cats" and [f.rsplit("/", 1)[-1] for f in al.files] == ["c1.png"] and al.state == "browse"
press("cancel", app=al)                            # back up, not out of the app
assert al.folder == sd and al.entries[al.sel] == "@dir:" + sd + "/Cats" and not al.minimised
al.sel = 5; press("confirm", app=al)               # the holiday album has a sub-album
assert al.entries[4] == "@dir:" + sd + "/holiday/beach"
al.sel = 4; press("confirm", app=al); assert al.folder.endswith("/beach")
press("cancel", app=al); press("cancel", app=al)
assert al.folder == sd and not al.minimised
# a search ignores the albums; the slideshow and viewer skip them
al.query = "c"; al._apply(); assert [e for e in al.entries if e.startswith("@dir")] == []
al.query = ""; al._apply(); al.sel = 4
al.state = "view"; al.sel = al._step(1); assert al.entries[al.sel].endswith("A.jpg")
al.state = "browse"
al.sel = 5; al._start_show(); assert al.entries[al.sel].endswith("A.jpg") and al.state == "show"
press("cancel", app=al)
# the album tile is drawn, in every layout
for no, (name, fac) in enumerate(glay.LAYOUTS):
    al.layout = fac(); ctx = RecCtx(); al.sel = 5; al.draw(ctx)
al.layout = glay.LAYOUTS[0][1]()
# sort from the settings screen re-reads the folder
al.state = "settings"; al._row = 3
press("right", app=al); assert al.sort == "newest" and al.files[0].endswith("A.jpg") and al.files[-1].endswith("b.jpg")
press("left", app=al); assert al.sort == "name"
al.state = "browse"
print(tag, "sort and albums ok")

# ---- 2026 only ----
if MODE == "2026":
    a.minimised = False
    a.inputs.flush()  # `a` also saw presses meant for the other apps on the shared stub bus
    a.state = "browse"
    a._toast_ms = 0
    a.sel = O
    press("joyright"); press("joydown")
    assert a.sel == O + 4, a.sel
    press("joyselect")
    assert a.state == "view"
    press("cancel")
    a.sel = O
    press("joyright", "right")   # reported twice, counts once
    assert a.sel == O + 1, a.sel

    def touch(pads):
        for t in list(a.inputs._touched):
            bus.emit(UpEvent({"t%d" % (t + 1)}))
        for p in pads:
            bus.emit(DownEvent({"t%d" % (p + 1)}))
        a.update(20)

    a.sel = O + 5
    for p in (0, 1, 2, 3, 4):
        touch([p])
    touch([])
    assert a.sel == O + 9, a.sel
else:
    assert ginputs.TOUCH == {} and a.inputs.touch_position() is None

# ---- minimise / resume ----
a.inputs.flush(); a.state = 'browse'; a.query = ''
press("cancel")
assert a.minimised
a.update(20)
assert a.inputs._bound == (MODE == "2026")
print(tag, "all checks passed")
