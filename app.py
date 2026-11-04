import app
import random
from math import pi

from .layouts import LAYOUTS
from .inputs import Inputs, PADS
from .touch_scroll import TouchScroller
from . import imginfo
from . import scanner
from . import thumbs
from . import storage
from . import keep
from . import stage
from . import hdmi

LAYOUT = 0                 # index into LAYOUTS
TOUCH_STEP = 1.0           # pads of finger travel round the ring per image
# Pictures with more pixels than this are not drawn (the badge can run out of
# memory decoding them). The screen is 240 x 240, so that is the starting point: find your
# badge's real limit with `tools/prepare.py --test-ladder`, then raise or
# lower this. 0 turns the check off.
MAX_PIXELS = 240 * 240
# The tiles of the home carousel: (name, colour). LEFT/RIGHT move between them, OK opens one.
HOME = (("Pictures", (0.45, 0.3, 0.7)), ("Slideshow", (0.1, 0.6, 0.3)),
        ("Search", (0.2, 0.5, 0.9)), ("Settings", (0.55, 0.55, 0.65)))
CHARS = "abcdefghijklmnopqrstuvwxyz0123456789 -_."   # on-badge search keyboard
DEBUG = False   # print progress lines (with free memory) over USB; turn off when not hunting a crash
COPY_MS = 80                         # longest slice of copying into the RAM disk in one frame
STAGE_AHEAD = 3                      # slideshow pictures kept ready in PSRAM
SORTS = (("name", "Name"), ("newest", "Newest first"), ("oldest", "Oldest first"))
SECONDS = (2, 60)                    # slideshow timer range


try:
    from time import ticks_ms, ticks_diff
except ImportError:       # not MicroPython (the PC tests)
    import time as _time

    def ticks_ms():
        return int(_time.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

TRACE_SLOW = False    # True: write frames slower than SLOW_MS to SLOW_LOG in flash, with what ran in them
SLOW_MS = 300
SLOW_LOG = storage.KEPT_ROOT + "/frames.txt"
SLOW_MAX = 120        # lines kept, so it can't fill the flash


def dbg(*a):
    if DEBUG:
        try:
            import gc
            print("gallery:", *a, "| free", gc.mem_free())
        except Exception:
            print("gallery:", *a)


def _special(e):
    """True for the cells that aren't pictures (albums: their names start with @)."""
    return e[0] == "@"


def _fit(w, h):
    """Rectangle (x, y, w, h) that fits a w x h picture on the 240x240 screen,
    keeping its shape, in ctx coordinates (origin at the centre)."""
    s = min(240 / w, 240 / h)
    dw = max(1, int(w * s + 0.5))
    dh = max(1, int(h * s + 0.5))
    return (-(dw // 2), -(dh // 2), dw, dh)


class GalleryApp(app.App):
    def __init__(self):
        super().__init__()
        self.inputs = Inputs(self)
        self.scroller = TouchScroller(step=TOUCH_STEP, period=PADS)
        saved = storage.load()
        try:
            self.seconds = max(SECONDS[0], min(SECONDS[1], int(saved.get("seconds", 5))))
        except ValueError:
            self.seconds = 5
        self.hdmi = hdmi.SecondScreen()
        self.hdmi_on = saved.get("hdmi") == "1"
        if self.hdmi_on:
            self.hdmi.switch_on()   # the TV mirrors the badge from the start, no HDMI Manager needed
        self._hdmi_path = None     # the picture the TV is showing
        self._hdmi_failed = False  # tried and couldn't: don't retry every frame
        self.shuffle = saved.get("shuffle") == "1"
        self.loop = saved.get("loop", "1") == "1"
        self.captions = saved.get("captions") == "1"
        self.sort = saved.get("sort", "name")
        if self.sort not in [s for s, _ in SORTS]:
            self.sort = "name"
        try:
            self.layout_no = int(saved.get("layout", LAYOUT)) % len(LAYOUTS)
        except ValueError:
            self.layout_no = LAYOUT
        self.layout = LAYOUTS[self.layout_no][1]()
        self._bigs = {}        # picture -> its 240 px copy (focus ring), or None
        try:
            keep.size = int(saved.get("keep_px", keep.size))
            if keep.size not in keep.SIZES:
                keep.size = keep.SIZES[0]
        except ValueError:
            pass
        self._thumbs = {}      # picture -> its thumbnail path, or None if not made yet
        self._row = 0          # settings screen: selected row
        self.state = "home"    # home, browse, view, search, settings, storage or show
        self._tile = 0         # home carousel: selected tile
        self._shown = None     # picture the viewer has measured
        self._rect = None      # where to draw it
        self._note = None      # lines to show instead, if it can't be drawn
        self._wait = False     # too big: a shrunk copy is being made
        self._small = None     # (picture, its shrunk copy or None), once tried
        self._draw_path = None # what the viewer actually draws
        self._caption = None   # (file name, size) for the captions setting
        self._order = []       # slideshow order (entry numbers)
        self._ram = None       # its staged copy in the RAM disk, if any
        self._kept = False     # the picture in the viewer is kept in flash
        self._toast_text = None
        self._toast_ms = 0
        self._defer = False
        self._pending = None   # a slow job to run next frame (after a message is up)
        self._q = ""           # search text being typed
        self._pick = 0         # letter on the on-badge search keyboard
        self._opts = []        # storage choices
        self._opt = 0
        self._job = ""         # what the background step did this frame (for the slow-frame log)
        self._lap = ""         # timings of the last HDMI picture
        self._slow_n = 0
        if TRACE_SLOW:
            try:
                open(SLOW_LOG, "w").close()     # a fresh slow-frame log for each run
            except Exception:
                pass
        self._since = 0        # slideshow clock, ms
        self._paused = False
        self._prepared = set() # slideshow pictures made ready
        self._show_ready = True  # (with HDMI on) the first ones are ready, so the TV may be taken over
        self._views = {}       # picture -> the small file the slideshow draws
        self.query = ""
        self._open(storage.current(), root=storage.current())

    # ---- what is shown ----------------------------------------------
    def _open(self, folder, root=None):
        """Switch to the pictures in a folder (root: the top of this storage, for going back up)."""
        self.folder = folder
        if root:
            self.root = root
        self.pics = scanner.list_images(folder, self.sort)
        self.albums = ["@dir:" + d for d in scanner.list_dirs(folder)] if folder != storage.KEPT else []
        self.query = ""
        self._thumbs = {}
        self._bigs = {}
        self._apply()

    def _thumb(self, path):
        """Thumbnail path of a picture if there is one, else None. Looked up once."""
        if path not in self._thumbs:
            t = scanner.thumb_path(path)
            self._thumbs[path] = t if scanner.exists(t) else None
        return self._thumbs[path]

    def _apply(self, sel=None):
        """Rebuild the cell list: the albums, then the pictures that match the search."""
        q = self.query.lower()
        self.files = [p for p in self.pics if q in p.rpartition("/")[2].lower()]
        albums = self.albums if not q else []     # a search looks at pictures only
        self.entries = albums + self.files
        self._first = len(albums)                 # where the pictures start
        if sel is None:
            sel = self._first if self.files else 0
        self.sel = max(0, min(len(self.entries) - 1, sel))
        if hasattr(self.layout, "reset"):
            self.layout.reset(len(self.entries))   # a layout that moves pictures starts again
        self._shown = None

    def _step(self, d):
        """Next picture (d = 1) or previous (d = -1), wrapping, skipping the albums."""
        n = len(self.entries)
        j = self.sel
        for _ in range(n):
            j = (j + d) % n
            if not _special(self.entries[j]):
                return j
        return self.sel

    def _slow(self, line):
        """Append a line to the slow-frame log in flash (read it with mpremote afterwards)."""
        if self._slow_n >= SLOW_MAX:
            return
        self._slow_n += 1
        try:
            with open(SLOW_LOG, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _toast(self, text, ms=1500):
        self._toast_text = text
        self._toast_ms = ms

    # ---- input -------------------------------------------------------
    def update(self, delta):
        self.inputs.bind()  # no-op unless we were unbound on minimise
        if self._toast_ms > 0:
            self._toast_ms -= delta
        self._clock(delta)

        steps = self.scroller.update(self.inputs.touch_position())
        if steps and self.state in ("browse", "view", "show") and self.entries:
            if self.state == "browse":
                for _ in range(abs(steps)):
                    self.sel = self.layout.move(self.sel, "RIGHT" if steps > 0 else "LEFT", len(self.entries))
            elif self.files:
                for _ in range(abs(steps)):
                    d = 1 if steps > 0 else -1
                    self.sel = self._show_step(self.sel, d) if self.state == "show" else self._step(d)

        for key in self.inputs.keys(delta):
            if self._key(key):
                return
        if self.hdmi.active and self.state not in ("view", "show"):
            self.hdmi.stop()         # only the viewer and slideshow use the second screen: the mirror takes the TV back
            self._hdmi_path = None
        self.hdmi.keepalive(delta)   # the TV shows static if it is left alone for half a second
        # after the keys: a slow job flushes presses made while it ran, not this frame's
        self._job = ""
        t0 = ticks_ms()
        self._background()
        if TRACE_SLOW and (delta > SLOW_MS or ticks_diff(ticks_ms(), t0) > SLOW_MS):
            self._slow("frame %d ms, background %d ms: %s | %s | %s" % (
                delta, ticks_diff(ticks_ms(), t0), self._job or "-", self.state, self._lap))

    def _key(self, key):
        """One key press. True if the app is leaving."""
        if key == "CANCEL":
            return self._cancel()
        getattr(self, "_k_" + self.state)(key)
        return False

    def _cancel(self):
        if self.state == "show":
            stage.stop()
            self.state = "home"
        elif self.state == "view":
            self.state = "browse"
        elif self.state == "storage":
            self.state = "settings"
        elif self.state in ("search", "settings"):
            self.state = "home"
        elif self.state == "browse" and self.query:
            self.query = ""
            self._apply()
        elif self.state == "browse" and self.folder != self.root and self.folder.startswith(self.root):  # up out of an album
            came_from = "@dir:" + self.folder
            self._open(self.folder.rpartition("/")[0])
            if came_from in self.entries:
                self.sel = self.entries.index(came_from)
        elif self.state == "browse":
            self.state = "home"
        else:
            self.hdmi.stop()
            self.inputs.unbind()
            self.minimise()
            return True
        return False

    def _k_home(self, key):
        if key in ("RIGHT", "NEXT", "DOWN", "LEFT", "PREV", "UP"):
            self._tile = (self._tile + (1 if key in ("RIGHT", "NEXT", "DOWN") else -1)) % len(HOME)
        elif key == "CONFIRM":
            name = HOME[self._tile][0]
            if name == "Pictures":
                self.state = "browse"
            elif name == "Slideshow":
                self._start_show()
            elif name == "Search":
                self._q = self.query
                self.state = "search"
            else:
                self._row = 0
                self.state = "settings"

    def _k_browse(self, key):
        n = len(self.entries)
        if not n:
            return
        if len(key) == 1:  # a letter on a USB keyboard
            self._jump(key)
        elif key in ("NEXT", "PREV"):
            self.sel = (self.sel + (1 if key == "NEXT" else -1)) % n
        elif key == "CONFIRM":
            e = self.entries[self.sel]
            if hasattr(self.layout, "swap") and self.layout.swap(self.sel, n):
                pass                      # the honeycomb: it went to the middle
            elif e.startswith("@dir:"):
                self._open(e[5:])
            else:
                self.state = "view"
        elif key in ("UP", "DOWN", "LEFT", "RIGHT"):
            self.sel = self.layout.move(self.sel, key, n)

    def _k_view(self, key):
        if len(key) == 1:
            self._jump(key)
        elif key in ("RIGHT", "DOWN", "NEXT"):
            self.sel = self._step(1)
        elif key in ("LEFT", "UP", "PREV"):
            self.sel = self._step(-1)
        elif key == "CONFIRM":  # keep in / remove from flash
            path = self.entries[self.sel]
            self._toast("Removing..." if keep.has(path) else "Keeping...", 60000)
            self._pending = lambda: self._do_keep(path)
            self._defer = True  # let the message be drawn first

    def _do_keep(self, path):
        if keep.has(path):
            keep.remove(path)
            msg = "Removed"
            if self.folder == storage.KEPT:  # it was in this list
                self.pics = scanner.list_images(storage.KEPT, self.sort)
                self._apply(self.sel)
                if not self.files:
                    self.state = "browse"
        else:
            r = keep.add(path)
            msg = {"kept": "Kept %d/%d" % (keep.count(), keep.MAX_KEEP),
                   "replaced": "Kept (oldest dropped)",
                   "already": "Already kept",
                   "full": "Flash is full",
                   "failed": "Can't keep it"}[r]
        self._shown = None
        self.inputs.flush()
        self._toast(msg)

    def _k_search(self, key):
        if len(key) == 1:
            self._q = (self._q + key)[:16]
        elif key == "NEXT":
            self._q = (self._q + " ")[:16]
        elif key in ("PREV", "LEFT"):
            self._q = self._q[:-1]
        elif key == "RIGHT":
            self._q = (self._q + CHARS[self._pick])[:16]
        elif key == "DOWN":
            self._pick = (self._pick + 1) % len(CHARS)
        elif key == "UP":
            self._pick = (self._pick - 1) % len(CHARS)
        elif key == "CONFIRM":
            self.query = self._q.strip()
            self._apply()
            self.state = "browse"

    ROWS = ("Source", "Layout", "Slide timer", "Slide order", "Loop slideshow", "Captions",
            "HDMI screen", "Kept size", "Sort", "Clear kept")

    def _k_settings(self, key):
        if key in ("UP", "PREV"):
            self._row = max(0, self._row - 1)
        elif key in ("DOWN", "NEXT"):
            self._row = min(len(self.ROWS) - 1, self._row + 1)
        elif key in ("LEFT", "RIGHT"):
            d = 1 if key == "RIGHT" else -1
            r = self.ROWS[self._row]
            if r == "Layout":
                self.layout_no = (self.layout_no + d) % len(LAYOUTS)
                self.layout = LAYOUTS[self.layout_no][1]()
                storage.save(layout=self.layout_no)
            elif r == "Slide timer":
                self.seconds = max(SECONDS[0], min(SECONDS[1], self.seconds + d))
                storage.save(seconds=self.seconds)
            elif r == "Slide order":
                self.shuffle = not self.shuffle
                storage.save(shuffle=int(self.shuffle))
            elif r == "Loop slideshow":
                self.loop = not self.loop
                storage.save(loop=int(self.loop))
            elif r == "Captions":
                self.captions = not self.captions
                storage.save(captions=int(self.captions))
            elif r == "HDMI screen":
                self.hdmi_on = not self.hdmi_on
                storage.save(hdmi=int(self.hdmi_on))
                self._hdmi_failed = False
                if self.hdmi_on and not self.hdmi.switch_on():
                    self._toast(self.hdmi.error)
                if not self.hdmi_on:
                    self.hdmi.stop()   # the mirror takes over again
                    self._hdmi_path = None
            elif r == "Kept size":
                sizes = keep.SIZES
                keep.size = sizes[(sizes.index(keep.size) + d) % len(sizes)]
                storage.save(keep_px=keep.size)
            elif r == "Sort":
                names = [s for s, _ in SORTS]
                self.sort = names[(names.index(self.sort) + d) % len(names)]
                storage.save(sort=self.sort)
                self.pics = scanner.list_images(self.folder, self.sort)
                self._apply()
        elif key == "CONFIRM" and self.ROWS[self._row] == "Source":
            self._start_storage()
        elif key == "CONFIRM" and self.ROWS[self._row] == "Clear kept":
            for p in scanner.list_images(storage.KEPT):
                keep.remove(p)
            if self.folder == storage.KEPT:
                self.pics = []
                self._apply()
            self._toast("Cleared")

    def _start_storage(self):
        self._opts = []
        for label, folder in storage.choices():
            if folder == storage.KEPT:
                info = "%d/%d kept" % (keep.count(), keep.MAX_KEEP)
            else:
                info = "%d pictures" % len(scanner.list_images(folder))
            self._opts.append((label, folder, info))
        self._opt = 0
        for i, o in enumerate(self._opts):
            if o[1] == self.folder:
                self._opt = i
        self.state = "storage"

    def _k_storage(self, key):
        if key in ("UP", "LEFT", "PREV"):
            self._opt = max(0, self._opt - 1)
        elif key in ("DOWN", "RIGHT", "NEXT"):
            self._opt = min(len(self._opts) - 1, self._opt + 1)
        elif key == "CONFIRM":
            folder = self._opts[self._opt][1]
            storage.save(folder=folder)
            self._open(folder, root=folder)
            self.state = "browse"

    def _start_show(self):
        if not self.files:
            self._toast("No pictures")
            return
        if self.sel < self._first:   # an album is selected
            self.sel = self._first
        dbg("slideshow: start, stage.start")
        stage.start()
        dbg("slideshow: staged disk ready")
        self._order = list(range(self._first, len(self.entries)))
        if self.shuffle:   # the one on screen first, then the rest in a random order
            rest = [i for i in self._order if i != self.sel]
            for i in range(len(rest) - 1, 0, -1):
                j = random.randrange(i + 1)
                rest[i], rest[j] = rest[j], rest[i]
            self._order = [self.sel] + rest
        self._prepared = set()
        self._views = {}
        self._since = 0
        self._paused = False
        self._shown = None
        self._show_ready = not self.hdmi_on   # with HDMI on, the first pictures are prepared before the TV is taken over
        self.state = "show"

    def _k_show(self, key):
        if key == "CONFIRM":
            self._paused = not self._paused
            self._toast("Paused" if self._paused else "Playing")
        elif key in ("UP", "DOWN"):
            d = 1 if key == "UP" else -1
            self.seconds = max(SECONDS[0], min(SECONDS[1], self.seconds + d))
            storage.save(seconds=self.seconds)
            self._toast("%d s" % self.seconds)
        elif key in ("RIGHT", "NEXT", "LEFT", "PREV"):
            self.sel = self._show_step(self.sel, 1 if key in ("RIGHT", "NEXT") else -1)
            self._since = 0

    def _clock(self, delta):
        """Slideshow timer: move on when the time is up and the next picture is ready."""
        if self.state != "show" or self._paused or not self.files:
            return
        self._since += delta
        if self._since >= self.seconds * 1000:
            if not self.loop and self._order.index(self.sel) == len(self._order) - 1:
                stage.stop()
                self.state = "home"
                self._toast("End of slideshow")
                return
            nxt = self._show_step(self.sel, 1)
            if self.entries[nxt] in self._prepared:
                self.sel = nxt
                self._since = 0

    def _background(self):
        """Work done between frames, one job per frame so the screen keeps
        moving: a pending job, shrinking the picture being viewed, getting the
        slideshow's next pictures ready, or making a missing thumbnail."""
        if self._pending:
            if self._defer:
                self._defer = False
                return
            job, self._pending = self._pending, None
            self._job = "pending job"
            job()
            return
        if self._hdmi_sync():
            self._job = "hdmi picture"
            return
        if self.state == "show":
            self._job = "prepare next"
            self._prepare_next()
            return
        if not thumbs.available or not self.files:
            return
        if self.state == "view":
            if self._wait:  # the viewer put up "Resizing" last frame
                self._wait = False
                path = self.entries[self.sel]
                self._small = (path, thumbs.shrunk(path))
                self._shown = None  # measure again, now with the small copy
                self.inputs.flush()  # presses made while we were busy
            return
        if self.state != "browse":
            return
        shown = self.layout.tiles(self.sel, len(self.entries))
        shown.sort(key=lambda t: t[0] != self.sel)   # the selected tile first
        for t in shown:
            path = self.entries[t[0]]
            if not _special(path) and self._thumb(path) is None and not thumbs.failed(path):
                if thumbs.make(path):
                    self._thumbs[path] = scanner.thumb_path(path)
                self.inputs.flush()
                return

    def _hdmi_sync(self):
        """Put the picture being viewed on the TV. True if that took this frame."""
        if not self.hdmi_on or self.state not in ("view", "show"):
            return False
        if self.state == "show" and not self._show_ready and not self.hdmi.active:
            return False        # still getting the first pictures ready: leave the TV on the mirror
        path = self.entries[self.sel]
        if self._shown != path or not self._rect or self._hdmi_path == path:
            return False        # not measured yet, can't be drawn, or already up
        if not self.hdmi.active:
            if self._hdmi_failed:
                return False
            dbg("hdmi: starting second screen")
            if not self.hdmi.start():
                self._hdmi_failed = True
                self._toast(self.hdmi.error)
                return False
        try:
            dbg("hdmi: draw", path.rsplit("/", 1)[-1])
            self.hdmi.refresh()      # the draw below is slow: start its silence from now
            t0 = ticks_ms()
            c = self.hdmi.ctx()
            c.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
            try:
                c.image(self._ram or self._draw_path, *self._rect)
            except Exception:
                if not self._ram:
                    raise
                stage.disable()
                self._ram = None
                c.image(self._draw_path, *self._rect)
            if self.captions and self._caption:
                self._text(c, self._caption[0][:20], 0, 100, 11, bg=True)
            t1 = ticks_ms()
            self.hdmi.show(c)
            self._lap = "%s: draw %d ms, send %d ms" % (path.rsplit("/", 1)[-1], ticks_diff(t1, t0), ticks_diff(ticks_ms(), t1))
            self._hdmi_path = path
        except Exception as e:
            print("gallery: HDMI draw failed", repr(e))
            self.hdmi.stop()
            self._hdmi_failed = True
            self._toast("HDMI: " + type(e).__name__)
        self.inputs.flush()
        return True

    def deinit(self):
        self.hdmi.stop()

    def _prepare_next(self):
        """Slideshow: shrink the current and next few pictures if need be and
        copy them into the PSRAM disk. One picture per frame."""
        window = []
        j = self.sel
        for _ in range(min(len(self.files), STAGE_AHEAD + 1)):
            window.append(self.entries[j])
            j = self._show_step(j, 1)
        self._prepared &= set(window)  # the ones left behind are dropped from the RAM disk below
        # A copy is done in slices of about COPY_MS a frame: one long copy would starve the
        # HDMI keep-alive, and the hexpansion shows static after half a second of silence.
        cur = stage.copying()
        if cur and cur not in self._views.values():
            stage.cancel()
            cur = None
        if cur:
            if stage.step(COPY_MS):
                self._prepared.add(next(p for p, v in self._views.items() if v == cur))
            return
        for p in window:
            if p not in self._prepared:
                view = p
                size = imginfo.size(p)
                if size and MAX_PIXELS and size[0] * size[1] > MAX_PIXELS and thumbs.available:
                    view = thumbs.shrunk(p) or p      # (slow, but only the first time for each picture)
                    self.inputs.flush()
                self._views[p] = view
                dbg("prepare", view.rsplit("/", 1)[-1])
                if not stage.begin(view) or stage.step(COPY_MS):
                    self._prepared.add(p)
                return
        if not self._show_ready and all(p in self._prepared for p in window):
            self._show_ready = True     # now the TV can be taken over, and the first picture gets its full time
            self._since = 0
        stage.keep_only([self._views[p] for p in window if p in self._views])

    def _show_step(self, j, d):
        """The picture after (d = 1) or before (d = -1) entry j in the slideshow's order, wrapping."""
        try:
            i = self._order.index(j)
        except ValueError:
            i = 0
        return self._order[(i + d) % len(self._order)]

    def _jump(self, ch):
        """Select the next image (after the current one, wrapping) whose
        file name starts with the typed letter."""
        n = len(self.entries)
        for i in range(1, n + 1):
            j = (self.sel + i) % n
            if not _special(self.entries[j]) and self.entries[j].rsplit("/", 1)[-1].lower().startswith(ch):
                self.sel = j
                return

    # ---- drawing -----------------------------------------------------
    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        if self.state == "home":
            self._draw_home(ctx)
        elif self.state == "search":
            self._draw_search(ctx)
        elif self.state == "storage":
            self._draw_storage(ctx)
        elif self.state == "settings":
            self._draw_settings(ctx)
        elif self.state in ("view", "show"):
            self._draw_view(ctx)
        else:
            self._draw_browse(ctx)
        if self._toast_ms > 0 and self._toast_text:
            self._text(ctx, self._toast_text, 0, 88, 14, bg=True)
        ctx.restore()

    def _text(self, ctx, text, x, y, size, bg=False, rgb=(1, 1, 1)):
        ctx.font_size = size
        ctx.text_align = ctx.CENTER
        ctx.text_baseline = ctx.MIDDLE
        if bg:
            w = len(text) * size * 0.6 + 12
            ctx.rgb(0, 0, 0).rectangle(x - w / 2, y - size, w, size * 2).fill()
        ctx.rgb(*rgb)
        ctx.move_to(x, y).text(text)

    def _message(self, ctx, *lines, dy=0):
        y = dy - 9 * (len(lines) - 1)
        for line in lines:
            self._text(ctx, line[:22], 0, y, 14)
            y += 18

    def _draw_search(self, ctx):
        self._text(ctx, "Search", 0, -85, 16, rgb=(0.5, 0.8, 1))
        self._text(ctx, (self._q + "_")[-14:], 0, -50, 20)
        ch = CHARS[self._pick]
        self._text(ctx, "space" if ch == " " else "< %s >" % ch, 0, -10, 26, rgb=(1, 0.9, 0.3))
        q = self._q.strip().lower()
        n = len([p for p in self.pics if q in p.rpartition("/")[2].lower()])
        self._text(ctx, "%d match%s" % (n, "" if n == 1 else "es"), 0, 30, 14)
        self._text(ctx, "UP/DN letter  R add  L del", 0, 65, 11)
        self._text(ctx, "OK search  F cancel", 0, 82, 11)

    def _draw_storage(self, ctx):
        self._text(ctx, "Storage", 0, -85, 16, rgb=(1, 0.7, 0.4))
        first = max(0, min(self._opt - 1, len(self._opts) - 3))
        for k, (label, folder, info) in enumerate(self._opts[first:first + 3]):
            i = first + k
            y = -45 + k * 42
            if i == self._opt:
                ctx.rgb(1, 1, 1)
                ctx.line_width = 2
                ctx.rectangle(-85, y - 18, 170, 38).stroke()
            self._text(ctx, ("* " if folder == self.folder else "") + label, 0, y - 6, 15)
            self._text(ctx, info, 0, y + 10, 11, rgb=(0.7, 0.7, 0.7))
        if len(self._opts) == 1:
            self._text(ctx, "no SD card found", 0, 85, 11)

    def _album_cell(self, ctx, e, x, y, w, h):
        name = e.rsplit("/", 1)[-1]
        ctx.rgb(0.55, 0.45, 0.1).rectangle(x, y, w, h).fill()
        if w < 60:
            self._text(ctx, name[:5], x + w // 2, y + h // 2, 11)
        else:
            k = 1 if h < 90 else 1.8
            self._text(ctx, name[:9], x + w // 2, y + h // 2 - 7 * k, 13 * k)
            self._text(ctx, "album", x + w // 2, y + h // 2 + 9 * k, 11 * k, rgb=(0.9, 0.9, 0.9))

    def _home_sub(self, name):
        """The small line under a home tile's name."""
        if name == "Pictures":
            where = "Flash" if self.root == storage.KEPT else self.root.split("/")[1][:9]
            return "%d in %s" % (len(self.files), where)
        if name == "Slideshow":
            return "%d s each" % self.seconds
        if name == "Search":
            return self.query[:12] or "by name"
        return LAYOUTS[self.layout_no][0][:12]

    def _icon(self, ctx, name, rgb):
        """A big simple icon for a home tile, drawn round (0, -30)."""
        ctx.rgb(*rgb)
        ctx.line_width = 6
        if name == "Pictures":
            for dx in (-30, 4):
                for dy in (-64, -30):
                    ctx.rectangle(dx, dy, 26, 26).fill()
        elif name == "Slideshow":
            ctx.begin_path()
            ctx.move_to(-22, -66)
            ctx.line_to(30, -30)
            ctx.line_to(-22, 6)
            ctx.close_path()
            ctx.fill()
        elif name == "Search":
            ctx.begin_path()
            ctx.arc(-6, -36, 26, 0, 2 * pi, 0)
            ctx.stroke()
            ctx.begin_path()
            ctx.move_to(13, -17)
            ctx.line_to(36, 6)
            ctx.stroke()
        else:
            for v, k in ((-56, -14), (-30, 14), (-4, -4)):   # three sliders and their knobs
                ctx.rectangle(-34, v - 2, 68, 4).fill()
                ctx.begin_path()
                ctx.arc(k, v, 8, 0, 2 * pi, 0)
                ctx.fill()

    def _draw_home(self, ctx):
        name, rgb = HOME[self._tile]
        self._icon(ctx, name, rgb)
        self._text(ctx, name, 0, 36, 24, rgb=rgb)
        self._text(ctx, self._home_sub(name), 0, 62, 13, rgb=(0.75, 0.75, 0.75))
        for i in range(len(HOME)):   # one dot per tile
            c = 1.0 if i == self._tile else 0.35
            ctx.rgb(c, c, c)
            ctx.begin_path()
            ctx.arc(-24 + 16 * i, 88, 4, 0, 2 * pi, 0)
            ctx.fill()
        self._text(ctx, "<", -88, -10, 22, rgb=(0.6, 0.6, 0.6))
        self._text(ctx, ">", 88, -10, 22, rgb=(0.6, 0.6, 0.6))

    def _outline(self, ctx, x, y, w, h):
        """Begin the path of a tile's shape: a rectangle, or a hexagon."""
        if self.layout.shape == "hex":
            pts = self.layout.outline(x, y, w, h)
            ctx.begin_path()
            ctx.move_to(*pts[0])
            for p in pts[1:]:
                ctx.line_to(*p)
            ctx.close_path()
        elif self.layout.shape == "circle":
            ctx.begin_path()
            ctx.arc(x + w / 2, y + h / 2, w / 2, 0, 2 * pi, 0)
        else:
            ctx.begin_path()
            ctx.rectangle(x, y, w, h)

    def _draw_tile(self, ctx, path, x, y, w, h, big):
        if _special(path):
            self._album_cell(ctx, path, x, y, w, h)
            return
        pic = self._thumb(path)
        if big:  # the focus tile: the 240 px copy if there is one, it is sharper
            if path not in self._bigs:
                self._bigs[path] = thumbs.shrunk(path, build=False)
            pic = self._bigs[path] or pic
        if pic:
            if self.layout.shape == "hex":   # square pictures, cut by the hexagon
                ctx.image(pic, x + (w - h) // 2, y, h, h)
            else:
                ctx.image(pic, x, y, w, h)
            return
        # no thumbnail: a colour from the name, and its first letter
        v = hash(path)
        ctx.rgb(0.15 + ((v >> 16) & 255) / 400,
                0.15 + ((v >> 8) & 255) / 400,
                0.15 + (v & 255) / 400).rectangle(x, y, w, h).fill()
        self._text(ctx, path.rsplit("/", 1)[-1][:1].upper(), x + w // 2, y + h // 2, 20)

    def _draw_browse(self, ctx):
        n = len(self.entries)
        for idx, x, y, w, h in (self.layout.tiles(self.sel, n) if n else ()):
            ctx.save()
            self._outline(ctx, x, y, w, h)
            ctx.clip()
            self._draw_tile(ctx, self.entries[idx], x, y, w, h,
                            self.layout.focus and idx == self.sel)
            ctx.restore()
            if idx == self.sel:
                self._outline(ctx, x, y, w, h)
                ctx.rgb(1, 1, 1)
                ctx.line_width = 3
                ctx.stroke()
        if not self.files:
            short = self.folder.split("/")[1] if self.folder.count("/") > 1 else self.folder
            self._text(ctx, ("No match: " + self.query)[:20] if self.query else "No images: " + short[:12],
                       0, 100, 12, bg=True)

    def _draw_settings(self, ctx):
        self._text(ctx, "Settings", 0, -88, 16, rgb=(0.8, 0.8, 0.9))
        where = "Flash" if self.root == storage.KEPT else self.root.split("/")[1][:9]
        vals = {
            "Source": where + " >",
            "Layout": "< %s >" % LAYOUTS[self.layout_no][0],
            "Slide timer": "< %d s >" % self.seconds,
            "Slide order": "< %s >" % ("Shuffle" if self.shuffle else "In order"),
            "Loop slideshow": "< %s >" % ("On" if self.loop else "Off"),
            "Captions": "< %s >" % ("On" if self.captions else "Off"),
            "HDMI screen": "< %s >" % ("Off" if not self.hdmi_on else "On" if self.hdmi.active or not self._hdmi_failed else "On: none"),
            "Kept size": "< %d px >" % keep.size,
            "Sort": "< %s >" % dict(SORTS)[self.sort],
            "Clear kept": "%d kept" % keep.count(),
        }
        shown = 4
        first = max(0, min(self._row - 1, len(self.ROWS) - shown))
        for k in range(shown):
            i = first + k
            y = -50 + k * 36
            if i == self._row:
                ctx.rgb(1, 1, 1)
                ctx.line_width = 2
                ctx.rectangle(-85, y - 16, 170, 34).stroke()
            self._text(ctx, self.ROWS[i], 0, y - 5, 11, rgb=(0.7, 0.7, 0.7))
            self._text(ctx, vals[self.ROWS[i]], 0, y + 9, 14)
        if first > 0:
            self._text(ctx, "^", 60, -76, 12)
        if first + shown < len(self.ROWS):
            self._text(ctx, "v", 60, 84, 12)
        self._text(ctx, {"Source": "OK choose", "Clear kept": "OK clear"}.get(self.ROWS[self._row], "L/R change"), 0, 100, 11)

    def _measure(self, path):
        """Work out how to show a picture before decoding it: where it goes,
        or why it can't be shown. A picture over MAX_PIXELS is replaced by a
        shrunk copy when imgtool is there to make one."""
        self._shown = path
        self._rect = None
        self._note = None
        self._draw_path = path
        self._ram = None
        self._caption = None
        self._kept = keep.has(path)
        tried = None
        if self._small and self._small[0] == path:
            tried = self._small          # _background() has just had a go
        self._small = None
        size = imginfo.size(path)
        if size is None:
            self._note = ("Can't read", path.rsplit("/", 1)[-1])
            return
        self._caption = (path.rsplit("/", 1)[-1], "%d x %d" % size)
        if MAX_PIXELS and size[0] * size[1] > MAX_PIXELS:
            small = None
            if thumbs.available:
                small = tried[1] if tried else thumbs.shrunk(path, build=False)
            if small:
                small_size = imginfo.size(small)
                if small_size and small_size[0] * small_size[1] <= MAX_PIXELS:
                    self._draw_path = small
                    self._rect = _fit(small_size[0], small_size[1])
                    self._ram = stage.lookup(small) if self.state == "show" else None
                    return
            elif thumbs.available and not tried and not thumbs.failed(path):
                self._note = ("Resizing...",)  # _background() does it next frame
                self._wait = True
                return
            self._note = ("Too big", "%d x %d" % size, "limit %d px" % MAX_PIXELS)
            return
        self._rect = _fit(size[0], size[1])
        self._ram = stage.lookup(path) if self.state == "show" else None

    def _draw_info(self, ctx, path):
        """The badge's own screen while the TV shows the picture."""
        self._text(ctx, "HDMI", 0, -92, 12, rgb=(0.4, 0.9, 1))
        name = path.rsplit("/", 1)[-1]
        self._text(ctx, name[:20], 0, -40, 15)
        if len(name) > 20:
            self._text(ctx, name[20:40], 0, -22, 15)
        if self._caption:
            self._text(ctx, self._caption[1], 0, 0, 12, rgb=(0.7, 0.7, 0.7))
        n = len(self.files)
        self._text(ctx, "%d / %d" % (self.entries.index(path) - self._first + 1, n), 0, 30, 18)
        if self.state == "show":
            frac = min(1.0, self._since / (self.seconds * 1000.0))
            ctx.rgb(0.4, 0.9, 1)
            ctx.line_width = 4
            ctx.begin_path()
            ctx.arc(0, 0, 105, -pi / 2, -pi / 2 + 2 * pi * frac, 0)
            ctx.stroke()
            self._text(ctx, "paused" if self._paused else "%d s" % self.seconds, 0, 62, 13)
        else:
            self._text(ctx, "L/R browse  OK keep", 0, 70, 11)
        if self._kept and self.state == "view":
            self._text(ctx, "kept", 0, 90, 11, rgb=(1, 0.9, 0.3))

    def _draw_view(self, ctx):
        path = self.entries[self.sel]
        if path != self._shown:
            self._measure(path)
        if self.hdmi.active and self._rect and self._hdmi_path is not None:
            self._draw_info(ctx, path)
            return
        if self._rect:
            try:
                try:
                    ctx.image(self._ram or self._draw_path, *self._rect)
                except Exception:
                    if not self._ram:
                        raise
                    print("gallery: can't draw from the RAM disk; using the card")
                    stage.disable()
                    self._ram = None
                    ctx.image(self._draw_path, *self._rect)
            except Exception as e:  # show why, instead of a black screen
                print("gallery: draw failed", self._draw_path, repr(e))
                self._rect = None
                self._note = ("Draw failed", type(e).__name__, self._draw_path.rsplit("/", 1)[-1])
                self._message(ctx, *self._note)
        else:
            self._message(ctx, *(self._note or ("Can't show", path.rsplit("/", 1)[-1])))
        if self.captions and self._caption:
            self._text(ctx, self._caption[0][:20], 0, 90, 11, bg=True)
            self._text(ctx, self._caption[1], 0, 104, 10, bg=True, rgb=(0.8, 0.8, 0.8))
        if self._kept and self.state == "view":
            self._text(ctx, "kept", 0, -100, 11, bg=True, rgb=(1, 0.9, 0.3))
        if self.state == "show" and self._paused:
            self._text(ctx, "paused", 0, -100, 11, bg=True)


__app_export__ = GalleryApp
