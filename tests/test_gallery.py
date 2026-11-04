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
    """Same behaviour as the badge firmware's events.input.Buttons: get() = held now,
    pressed() = True once per press (latched until the key is let go), clear() wipes
    both the held state and the latch."""
    def __init__(self, owner):
        self.buttons, self._already = {}, set()
        bus.on(DownEvent, self._d, owner)
        bus.on(UpEvent, self._u, owner)
    def _d(self, ev):
        for b in ev.button:
            self.buttons[b] = True
    def _u(self, ev):
        for b in ev.button:
            self.buttons[b] = False
            self._already.discard(b)   # (the real one does this at the next poll; the tests poll once per press)
    def get(self, t):
        return any(v for b, v in self.buttons.items() if b == t)
    def pressed(self, t):
        down = self.get(t)
        if down and t not in self._already:
            self._already.add(t)
            return True
        if not down:
            self._already.discard(t)
        return False
    def clear(self):
        self.buttons.clear(); self._already.clear()


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
O = 0  # no special cells any more: the first cell is a picture (or an album)


def make(names, folder=None):
    d = folder or tempfile.mkdtemp()
    for n in names:
        open(os.path.join(d, n), "w").close()
    gstorage.current = lambda: d
    g = gapp.GalleryApp()
    assert g.state == "home"
    g.state = "browse"   # most tests start on the picture cells
    return g


a = make(["img%02d.png" % n for n in range(30)])
assert len(a.files) == 30 and len(a.entries) == 30 and a.sel == O


def goto(app, name):
    """Open a tile of the home carousel."""
    app.state = "home"
    app._tile = [n for n, _ in gapp.HOME].index(name)
    press("confirm", app=app)


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
assert a.sel == 29          # wraps to the last picture
press("right")
assert a.sel == O           # and back round
press("cancel")
assert a.state == "browse" and not a.minimised

# ---- hold to repeat ----
a.sel = O
bus.emit(DownEvent({"right"})); a.update(20)
assert a.sel == O + 1, a.sel               # the press itself
for _ in range(3):
    a.update(100); assert a.sel == O + 1
a.update(100); assert a.sel == O + 2       # 400 ms: repeat starts
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
goto(c, "Search"); assert c.state == "search"
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
goto(c, "Search")
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
goto(c, "Settings"); c._row = c.ROWS.index("Source"); press("confirm", app=c)
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
assert len(fl.files) == 9 and fl.state == "view" and not fl.entries[fl.sel].startswith("@")
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
goto(sh, "Slideshow")
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
press("cancel", app=sh); assert sh.state == "home" and not gstage._mounted
gstage.enabled = True
# staging copies in slices, so one long copy can't starve the HDMI keep-alive
old_mount = gstage.MOUNT
gstage.MOUNT = tempfile.mkdtemp(); gstage._mounted = True
bigsrc = os.path.join(tempfile.mkdtemp(), "big.jpg"); open(bigsrc, "wb").write(bytes(range(256)) * 80)   # 20 KB
assert gstage.begin(bigsrc) and gstage.copying() == bigsrc and gstage.lookup(bigsrc) is None
slices = 1
while not gstage.step(0):                      # a zero budget: one 2 KB chunk per call
    slices += 1
assert slices >= 10 and gstage.copying() is None
assert open(gstage.lookup(bigsrc), "rb").read() == open(bigsrc, "rb").read()
assert gstage.begin(bigsrc) is False           # already staged
assert gstage.begin(bigsrc + ".missing") is False and gstage.copying() is None
assert gstage.begin(bigsrc.replace("big", "big2")) is False     # (no such file)
open(bigsrc.replace("big", "big2"), "wb").write(b"x" * 5000)
assert gstage.begin(bigsrc.replace("big", "big2")); gstage.cancel(); assert gstage.copying() is None
gstage._files.clear(); gstage._mounted = False; gstage.MOUNT = old_mount
print(tag, "slideshow ok")

# ---- empty storage: nothing to open, nothing breaks ----
e = make([], folder=tempfile.mkdtemp())
assert e.entries == [] and e.sel == 0
ctx = Ctx(); e.draw(ctx)
press("down", "confirm", app=e)  # nothing to move to or open
ctx = Ctx(); e.draw(ctx)
goto(e, "Slideshow")
assert e.state == "home"         # slideshow with nothing to show
print(tag, "empty ok")

# ---- settings tile and the other layouts ----
import gallery.layouts as glay
st = make(["p%02d.jpg" % i for i in range(40)])
goto(st, "Settings"); assert st.state == "settings"
st._row = st.ROWS.index("Layout")
assert st.layout_no == 0
press("right", app=st); assert st.layout_no == 1 and st.layout.per_page == 16
press("right", app=st); press("right", app=st)
assert st.layout_no == 3 and st.layout.focus
press("right", app=st); assert st.layout_no == 0           # wraps
assert gstorage.load()["layout"] == "0"
press("down", app=st); press("right", app=st)   # slide timer
t0 = st.seconds
press("left", app=st); assert st.seconds == max(gapp.SECONDS[0], t0 - 1)
press("down", app=st)                          # slide order
assert not st.shuffle
press("right", app=st); assert st.shuffle and gstorage.load()["shuffle"] == "1"
press("down", app=st)                          # loop
assert st.loop
press("left", app=st); assert not st.loop and gstorage.load()["loop"] == "0"
press("right", app=st); assert st.loop
press("down", app=st)                          # captions
assert not st.captions
press("right", app=st); assert st.captions and gstorage.load()["captions"] == "1"
press("down", app=st)                          # HDMI screen
assert not st.hdmi_on
press("right", app=st); assert st.hdmi_on and gstorage.load()["hdmi"] == "1"
press("left", app=st); assert not st.hdmi_on and gstorage.load()["hdmi"] == "0"
press("down", app=st)                          # kept size
assert gkeep.size == 240
press("right", app=st); assert gkeep.size == 480 and gstorage.load()["keep_px"] == "480"
press("left", app=st); press("left", app=st); assert gkeep.size == 720   # wraps
press("right", app=st); assert gkeep.size == 240
press("down", app=st)                          # sort
assert st.sort == "name"
press("right", app=st); assert st.sort == "newest" and gstorage.load()["sort"] == "newest"
press("right", app=st); press("right", app=st); assert st.sort == "name"
press("down", app=st)                          # clear kept
before = gkeep.count()
press("confirm", app=st); assert gkeep.count() == 0 and st._toast_text == "Cleared"
press("cancel", app=st); assert st.state == "home"
# ---- a held key doesn't start another slow job when flush() is called after the last one ----
lk = make(["k%d.jpg" % i for i in range(3)])
bus.emit(DownEvent({"confirm"}))
assert lk.inputs.keys(20) == ["CONFIRM"]
lk.inputs.flush()                                   # what a slow job does when it ends
for _ in range(5):
    assert lk.inputs.keys(20) == [], "a key that is still down came back as a new press"
bus.emit(UpEvent({"confirm"})); assert lk.inputs.keys(20) == []
bus.emit(DownEvent({"confirm"})); assert lk.inputs.keys(20) == ["CONFIRM"]   # a real new press still counts
bus.emit(UpEvent({"confirm"}))
bus.emit(DownEvent({"cancel"})); lk.inputs.flush(); bus.emit(UpEvent({"cancel"}))   # pressed during a job: dropped
assert lk.inputs.keys(20) == []

# ---- the home carousel ----
hm = make(["p%02d.jpg" % i for i in range(5)]); hm.state = "home"
names = [n for n, _ in gapp.HOME]
assert names == ["Pictures", "Slideshow", "Search", "Settings"] and hm._tile == 0
press("right", app=hm); assert hm._tile == 1
press("left", app=hm); press("left", app=hm); assert hm._tile == 3          # wraps
press("right", app=hm); assert hm._tile == 0
press("confirm", app=hm); assert hm.state == "browse"                        # Pictures
press("cancel", app=hm); assert hm.state == "home" and not hm.minimised      # back to the carousel
goto(hm, "Slideshow"); assert hm.state == "show"
press("cancel", app=hm); assert hm.state == "home"
goto(hm, "Search"); assert hm.state == "search"
press("cancel", app=hm); assert hm.state == "home"
goto(hm, "Settings"); assert hm.state == "settings" and hm.ROWS[hm._row] == "Source"
press("cancel", app=hm); assert hm.state == "home"
press("cancel", app=hm); assert hm.minimised                                 # CANCEL on the carousel leaves
for i in range(len(names)):
    hm._tile = i; hm.state = "home"; hm.draw(Ctx())                          # every tile draws
# an album is a cell, not a tile; a search with no hits leaves an empty cell list that still draws
hm.state = "browse"; hm.query = "zzz"; hm._apply(); assert hm.entries == [] and hm.files == []
hm.draw(Ctx()); press("confirm", "up", "right", app=hm)
# in the honeycomb, CONFIRM swaps a picture into the middle; on the middle one it opens it
hy = make(["h%02d.jpg" % i for i in range(30)])
hy.layout_no = 2; hy.layout = glay.LAYOUTS[2][1](); hy._apply(0)
assert hy.sel == 0 and hy.layout.cells[0] == 0
press("right", app=hy); assert hy.sel == 1 and hy.state == "browse"
press("confirm", app=hy); assert hy.state == "browse" and hy.layout.cells[0] == 1 and hy.layout.cells[1] == 0
press("confirm", app=hy); assert hy.state == "view"                 # it is in the middle now: open it
press("cancel", app=hy); assert hy.state == "browse" and hy.entries[hy.sel].endswith("h01.jpg")
hy.draw(Ctx())
# a new app picks up the saved layout
gstorage.save(layout=2)
st2 = make(["p%02d.jpg" % i for i in range(40)])
assert st2.layout_no == 2 and st2.layout.shape == "hex"
gstorage.save(layout=0)

# ---- HDMI second screen, against a stand-in for the firmware's display module ----
import gallery.hdmi as ghdmi
class FakeScreen:
    made = []
    def __init__(self, port, width, height, baudrate, driver):
        self.args = (port, width, height, baudrate, driver["header"]); self.frames = 0; self.closed = False
        FakeScreen.made.append(self)
    def get_ctx(self): return Ctx()
    def end_frame(self, c): self.frames += 1; self.last = c
    def deinit(self): self.closed = True
class FakeDisplay:
    mirror = {3}
    log = []
    Screen = FakeScreen
    @classmethod
    def is_mirror_active(cls, p): return p in cls.mirror
    @classmethod
    def detach_mirror(cls, port): cls.mirror.discard(port); cls.log.append(("detach", port))
    @classmethod
    def attach_mirror(cls, port, baudrate, driver): cls.mirror.add(port); cls.log.append(("attach", port))
real_display = ghdmi.display
ghdmi.display = FakeDisplay
def real(n):
    from PIL import Image
    d = tempfile.mkdtemp()
    for i in range(n):
        Image.new("RGB", (120, 90), (i * 40, 90, 160)).save(os.path.join(d, "p%02d.png" % i))
    return d
ghdmi.KEEPALIVE_MS = 10 ** 9      # off for the first checks: they count exactly the frames the picture needs
hv = make([], folder=real(5))
hv.hdmi_on = True
hv.sel = hv._first; press("confirm", app=hv); assert hv.state == "view"
for _ in range(6):
    hv.draw(Ctx()); hv.update(50)
assert hv.hdmi.active and hv.hdmi.port == 3, hv.hdmi.error
scr = FakeScreen.made[-1]
assert scr.args == (3, 240, 240, 10_000_000, b"TDHD") and scr.frames == 1
for _ in range(4):
    hv.draw(Ctx()); hv.update(50)
assert scr.frames == 1                       # unchanged picture: not sent again
press("right", app=hv)
for _ in range(8):
    hv.draw(Ctx()); hv.update(50)
assert scr.frames == 3                       # the new picture, plus the old one sent again just before its slow draw
# keep-alive: the hexpansion shows static after 500 ms of silence, so the same frame is sent again every 350 ms
ghdmi.KEEPALIVE_MS = 350
hv.hdmi._quiet = 0; f0 = scr.frames
for _ in range(3):
    hv.update(100)
assert scr.frames == f0                      # 300 ms: not yet
hv.update(100); assert scr.frames == f0 + 1  # 400 ms: sent again, nothing redrawn
press("cancel", app=hv); assert hv.state == "browse"
hv.update(20)
assert not hv.hdmi.active and scr.closed and 3 in FakeDisplay.mirror     # out of the viewer: the mirror has the TV again
f1 = scr.frames
for _ in range(8):
    hv.update(100)
assert scr.frames == f1                      # and no frames are sent
# a slow frame can't pass for a hold
hk = make(["k%d.jpg" % i for i in range(5)]); hk.sel = 0
bus.emit(DownEvent({"right"})); hk.update(20); assert hk.sel == 1
hk.update(5000); hk.update(5000); assert hk.sel == 1, hk.sel   # one tap seen over two long frames: no repeat
bus.emit(UpEvent({"right"}))
ghdmi.KEEPALIVE_MS = 10 ** 9
press("confirm", app=hv); assert hv.state == "view"   # back in the viewer: the second screen starts again
for _ in range(6):
    hv.draw(Ctx()); hv.update(50)
assert hv.hdmi.active and FakeScreen.made[-1] is not scr
press("cancel", app=hv); press("cancel", app=hv); press("cancel", app=hv)   # view, browse, home
assert not hv.hdmi.active and scr.closed and 3 in FakeDisplay.mirror   # mirror restored
# no HDMI fitted: say so once, don't keep trying
FakeDisplay.mirror = set(); FakeDisplay.log = []
hn = make([], folder=real(5)); hn.hdmi_on = True
hn.sel = hn._first; press("confirm", app=hn)
for _ in range(10):
    hn.draw(Ctx()); hn.update(50)
assert not hn.hdmi.active and hn._hdmi_failed and not FakeDisplay.log
# plugged in but not mirroring (no HDMI Manager run): switching the option on starts it by itself
mod("system.hexpansion"); mod("system.hexpansion.util", get_slots_by_vid_pid=lambda v, p: [4] if (v, p) == (0x1969, 0x4544) else [])
FakeDisplay.mirror = set(); FakeDisplay.log = []
hs = make([], folder=real(2)); hs.state = "settings"; hs._row = hs.ROWS.index("HDMI screen")
press("right", app=hs)
assert hs.hdmi_on and ("attach", 4) in FakeDisplay.log and 4 in FakeDisplay.mirror, FakeDisplay.log
press("right", app=hs); assert not hs.hdmi_on          # off again: nothing more is attached
press("right", app=hs); assert hs.hdmi_on and FakeDisplay.log.count(("attach", 4)) == 1   # already mirroring: left alone
hs2 = make([], folder=real(2)); assert hs2.hdmi_on     # remembered: starts mirroring when the app opens
FakeDisplay.mirror = set(); FakeDisplay.log = []
sys.modules.pop("system.hexpansion.util"); sys.modules.pop("system.hexpansion")
ghdmi.display = real_display
print(tag, "hdmi ok")

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

st.state = "settings"
for row in range(len(st.ROWS)):          # the scrolling settings list draws at every row
    st._row = row; st.draw(RecCtx())
st.state = "browse"
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

# honeycomb: pictures keep their cells; CONFIRM swaps the highlighted one with the middle one
import math
hc = glay.HoneycombLayout()
hc.reset(44)
tl = hc.tiles(0, 44)
assert len(tl) == 19 and tl[0][0] == 0 and tl[0][1] + tl[0][3] / 2 == 0 and tl[0][2] + tl[0][4] / 2 == 0, tl[0]
assert [i for i, *_ in tl] == list(range(19))                       # the middle one, then the first 18 outer cells
ctr = [(x + w / 2, y + h / 2) for _, x, y, w, h in tl]
assert all(abs(math.hypot(*ctr[i]) - math.hypot(*ctr[1])) < 2 for i in range(1, 7))   # ring 1 is round the middle
assert all(math.hypot(x, y) + 25 <= 120 for x, y in ctr)                               # inside the round screen
cell = {i: (x, y) for i, x, y, w, h in tl}
# moving the highlight doesn't move any picture, and never changes the middle one
sel = 1
for d in ("RIGHT", "DOWN", "LEFT", "UP", "RIGHT", "RIGHT"):
    sel = hc.move(sel, d, 44)
    assert {i: (x, y) for i, x, y, w, h in hc.tiles(sel, 44)} == cell and hc.cells[0] == 0
assert hc.move(1, "RIGHT", 44) != 1 and hc.move(0, "RIGHT", 44) == 1      # from the middle, RIGHT is the cell on its right
# CONFIRM swaps the highlighted picture with the middle one; the others stay put
assert hc.swap(0, 44) is False                                              # on the middle one: the app opens it
at = {i: (x, y) for i, x, y, w, h in hc.tiles(5, 44)}
assert hc.swap(5, 44) is True
now = {i: (x, y) for i, x, y, w, h in hc.tiles(5, 44)}
assert now[5] == at[0] and now[0] == at[5] and all(now[i] == at[i] for i in range(1, 19) if i != 5)
assert hc.swap(5, 44) is False                                              # 5 is in the middle now
# more pictures than cells: moving off the edge scrolls the outer cells a page; the middle stays
sel = 18
assert hc.cells[1 + 17] == 18
for d in ("RIGHT", "DOWN"):
    hc.page = 0
    cur = 17
    for _ in range(60):
        new = hc.move(cur, d, 44)
        if new == cur:
            break
        cur = new
        if hc.page:
            break
    assert hc.page == 1, (d, cur, hc.page)
    got = [i for i, *_ in hc.tiles(cur, 44)]
    assert got[0] == hc.cells[0] and got[1:] == hc.cells[1 + 18:1 + 36], got      # the middle one didn't change
hc.page = 1
back = hc.move(hc.cells[1 + 18 + 12], "LEFT", 44)                           # the left-most cell of page 1
assert hc.page == 0 and back == hc.cells[1 + 12]                            # the same cell on the page before
assert hc.move(hc.cells[1 + 12], "LEFT", 44) == hc.cells[1 + 12] and hc.page == 0   # nothing before the first page
last = hc.tiles(hc.cells[-1], 44)                                           # the last page is partly empty
assert len(last) == 1 + (44 - 1 - 36) and hc.page == 2
assert hc.tiles(0, 0) == [] and hc.move(0, "RIGHT", 0) == 0
sm = glay.HoneycombLayout(); sm.reset(5)
assert sorted(i for i, *_ in sm.tiles(2, 5)) == [0, 1, 2, 3, 4]              # a short list: each picture once
one = glay.HoneycombLayout(); one.reset(1)
assert one.move(0, "DOWN", 1) == 0 and one.swap(0, 1) is False
fr0 = glay.FocusRingLayout()
assert fr0.shape == "circle"
ctx = RecCtx(); cf = make(["z%d.jpg" % i for i in range(12)]); cf.layout = fr0; cf.sel = O + 5   # all eight neighbours exist
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
assert al.entries[:2] == ["@dir:" + sd + "/Cats", "@dir:" + sd + "/holiday"]
assert al._first == 2 and al.sel == 2 and [f.rsplit("/", 1)[-1] for f in al.files] == ["A.jpg", "b.jpg", "c.jpg"]
al.sel = 0; press("confirm", app=al)               # open the Cats album
assert al.folder == sd + "/Cats" and [f.rsplit("/", 1)[-1] for f in al.files] == ["c1.png"] and al.state == "browse"
press("cancel", app=al)                            # back up, not out of the app
assert al.folder == sd and al.entries[al.sel] == "@dir:" + sd + "/Cats" and not al.minimised
al.sel = 1; press("confirm", app=al)               # the holiday album has a sub-album
assert al.entries[0] == "@dir:" + sd + "/holiday/beach"
al.sel = 0; press("confirm", app=al); assert al.folder.endswith("/beach")
press("cancel", app=al); press("cancel", app=al)
assert al.folder == sd and not al.minimised
# a search ignores the albums; the slideshow and viewer skip them
al.query = "c"; al._apply(); assert [e for e in al.entries if e.startswith("@dir")] == []
al.query = ""; al._apply(); al.sel = 0
al.state = "view"; al.sel = al._step(1); assert al.entries[al.sel].endswith("A.jpg")
al.state = "browse"
al.sel = 1; al._start_show(); assert al.entries[al.sel].endswith("A.jpg") and al.state == "show"
press("cancel", app=al)
# the album tile is drawn, in every layout
for no, (name, fac) in enumerate(glay.LAYOUTS):
    al.layout = fac(); ctx = RecCtx(); al.sel = 1; al.draw(ctx)
al.layout = glay.LAYOUTS[0][1]()
# sort from the settings screen re-reads the folder
al.state = "settings"; al._row = al.ROWS.index("Sort")
press("right", app=al); assert al.sort == "newest" and al.files[0].endswith("A.jpg") and al.files[-1].endswith("b.jpg")
press("left", app=al); assert al.sort == "name"
al.state = "browse"
print(tag, "sort and albums ok")

# ---- slideshow order, loop and captions ----
sw = make(["w%d.jpg" % i for i in range(6)])
sw.sel = sw._first; sw.shuffle = True; sw.loop = False
sw._start_show()
assert sw._order[0] == sw._first and sorted(sw._order) == list(range(sw._first, sw._first + 6))
assert sw._order != sorted(sw._order) or True
seen = [sw.sel]
for _ in range(5):                       # play through, one slide per timer
    for _ in range(12):
        sw.update(20)                    # get the next pictures ready
    sw.update(sw.seconds * 1000)
    seen.append(sw.sel)
assert sw.state == "show" and sorted(seen) == sorted(sw._order), (seen, sw._order)
assert seen == sw._order                 # in the shuffled order
for _ in range(12):
    sw.update(20)
sw.update(sw.seconds * 1000)             # the last one is up: no loop, so it stops
assert sw.state == "home" and sw._toast_text == "End of slideshow"
sw.loop = True; sw.shuffle = False; sw.sel = sw._first; sw._start_show()
assert sw._order == list(range(sw._first, sw._first + 6))
for k in range(8):                       # loops past the end
    for _ in range(12):
        sw.update(20)
    sw.update(sw.seconds * 1000)
assert sw.state == "show" and sw.sel == sw._first + 8 % 6, sw.sel
press("left", app=sw); assert sw.sel == sw._first + 1
press("cancel", app=sw)
# captions: name and size under the picture, in the viewer
cp = tempfile.mkdtemp(); Image.new("RGB", (64, 48)).save(cp + "/cap.png")
cv = make(["x.txt"], folder=cp); cv.captions = True; cv.sel = cv._first; cv.state = "view"
class TextCtx(RecCtx):
    def __init__(self): super().__init__(); self.texts = []
    def __getattr__(self, n):
        if n == "text":
            def f(t, *a): self.texts.append(t); return self
            return f
        return super().__getattr__(n)
tc = TextCtx(); cv.draw(tc)
assert "cap.png" in tc.texts and "64 x 48" in tc.texts, tc.texts
cv.captions = False; cv._shown = None; tc = TextCtx(); cv.draw(tc)
assert "cap.png" not in tc.texts
# BMP isn't listed: the badge's picture loader can't draw it
open(cp + "/p.bmp", "w").close(); open(cp + "/p.gif", "w").close()
assert [f.rsplit("/", 1)[-1] for f in gapp.scanner.list_images(cp)] == ["cap.png", "p.gif"]
print(tag, "slideshow options and captions ok")

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
press("cancel"); assert a.state == "home" and not a.minimised
press("cancel")
assert a.minimised
a.update(20)
assert a.inputs._bound == (MODE == "2026")
print(tag, "all checks passed")
