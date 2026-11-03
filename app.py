import app
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

LAYOUT = 0                 # index into LAYOUTS
TOUCH_STEP = 1.0           # pads of finger travel round the ring per image
# Pictures with more pixels than this are not drawn (the badge can run out of
# memory decoding them). The screen is 240 x 240, so that is the starting point: find your
# badge's real limit with `tools/prepare.py --test-ladder`, then raise or
# lower this. 0 turns the check off.
MAX_PIXELS = 240 * 240
SEARCH, STORAGE, SHOW, SETTINGS = "@search", "@storage", "@show", "@settings"
SPECIAL = (SEARCH, STORAGE, SHOW, SETTINGS)   # the first tiles; not pictures
SHORT = {SEARCH: "Find", STORAGE: "SD", SHOW: "Show", SETTINGS: "Set"}  # on small tiles
CHARS = "abcdefghijklmnopqrstuvwxyz0123456789 -_."   # on-badge search keyboard
STAGE_AHEAD = 3                      # slideshow pictures kept ready in PSRAM
SECONDS = (2, 60)                    # slideshow timer range


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
        self.state = "browse"  # browse, view, search, storage or show
        self._shown = None     # picture the viewer has measured
        self._rect = None      # where to draw it
        self._note = None      # lines to show instead, if it can't be drawn
        self._wait = False     # too big: a shrunk copy is being made
        self._small = None     # (picture, its shrunk copy or None), once tried
        self._draw_path = None # what the viewer actually draws
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
        self._since = 0        # slideshow clock, ms
        self._paused = False
        self._prepared = set() # slideshow pictures made ready
        self._views = {}       # picture -> the small file the slideshow draws
        self.query = ""
        self._open(storage.current())

    # ---- what is shown ----------------------------------------------
    def _open(self, folder):
        """Switch to the pictures in a folder."""
        self.folder = folder
        self.pics = scanner.list_images(folder)
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
        """Rebuild the tile list: three special tiles, then the pictures that match the search."""
        q = self.query.lower()
        self.files = [p for p in self.pics if q in p.rpartition("/")[2].lower()]
        self.entries = list(SPECIAL) + self.files
        if sel is None:
            sel = len(SPECIAL) if self.files else 0
        if self.files and sel < len(SPECIAL):
            sel = len(SPECIAL)
        self.sel = max(0, min(len(self.entries) - 1, sel))
        self._shown = None

    def _step(self, d):
        """Next picture (d = 1) or previous (d = -1), wrapping, skipping the special tiles."""
        n = len(self.entries)
        j = self.sel
        for _ in range(n):
            j = (j + d) % n
            if self.entries[j] not in SPECIAL:
                return j
        return self.sel

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
        if steps and self.state in ("browse", "view", "show"):
            if self.state == "browse":
                self.sel = max(0, min(len(self.entries) - 1, self.sel + steps))
            elif self.files:
                for _ in range(abs(steps)):
                    self.sel = self._step(1 if steps > 0 else -1)

        for key in self.inputs.keys(delta):
            if self._key(key):
                return
        # after the keys: a slow job flushes presses made while it ran, not this frame's
        self._background()

    def _key(self, key):
        """One key press. True if the app is leaving."""
        if key == "CANCEL":
            return self._cancel()
        getattr(self, "_k_" + self.state)(key)
        return False

    def _cancel(self):
        if self.state == "show":
            stage.stop()
            self.state = "browse"
        elif self.state != "browse":
            self.state = "browse"
        elif self.query:
            self.query = ""
            self._apply()
        else:
            self.inputs.unbind()
            self.minimise()
            return True
        return False

    def _k_browse(self, key):
        n = len(self.entries)
        if len(key) == 1:  # a letter on a USB keyboard
            self._jump(key)
        elif key in ("NEXT", "PREV"):
            self.sel = (self.sel + (1 if key == "NEXT" else -1)) % n
        elif key == "CONFIRM":
            e = self.entries[self.sel]
            if e == SEARCH:
                self._q = self.query
                self.state = "search"
            elif e == STORAGE:
                self._start_storage()
            elif e == SHOW:
                self._start_show()
            elif e == SETTINGS:
                self._row = 0
                self.state = "settings"
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
                self.pics = scanner.list_images(storage.KEPT)
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

    ROWS = ("Layout", "Slide timer", "Kept size", "Clear kept")

    def _k_settings(self, key):
        if key in ("UP", "PREV"):
            self._row = max(0, self._row - 1)
        elif key in ("DOWN", "NEXT"):
            self._row = min(len(self.ROWS) - 1, self._row + 1)
        elif key in ("LEFT", "RIGHT"):
            d = 1 if key == "RIGHT" else -1
            if self._row == 0:
                self.layout_no = (self.layout_no + d) % len(LAYOUTS)
                self.layout = LAYOUTS[self.layout_no][1]()
                storage.save(layout=self.layout_no)
            elif self._row == 1:
                self.seconds = max(SECONDS[0], min(SECONDS[1], self.seconds + d))
                storage.save(seconds=self.seconds)
            elif self._row == 2:
                sizes = keep.SIZES
                keep.size = sizes[(sizes.index(keep.size) + d) % len(sizes)]
                storage.save(keep_px=keep.size)
        elif key == "CONFIRM" and self._row == 3:
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
            self._open(folder)
            self.state = "browse"

    def _start_show(self):
        if not self.files:
            self._toast("No pictures")
            return
        if self.entries[self.sel] in SPECIAL:
            self.sel = len(SPECIAL)
        stage.start()
        self._prepared = set()
        self._views = {}
        self._since = 0
        self._paused = False
        self._shown = None
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
            self.sel = self._step(1 if key in ("RIGHT", "NEXT") else -1)
            self._since = 0

    def _clock(self, delta):
        """Slideshow timer: move on when the time is up and the next picture is ready."""
        if self.state != "show" or self._paused or not self.files:
            return
        self._since += delta
        if self._since >= self.seconds * 1000:
            nxt = self._step(1)
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
            job()
            return
        if self.state == "show":
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
            if path not in SPECIAL and self._thumb(path) is None and not thumbs.failed(path):
                if thumbs.make(path):
                    self._thumbs[path] = scanner.thumb_path(path)
                self.inputs.flush()
                return

    def _prepare_next(self):
        """Slideshow: shrink the current and next few pictures if need be and
        copy them into the PSRAM disk. One picture per frame."""
        window = []
        j = self.sel
        for _ in range(min(len(self.files), STAGE_AHEAD + 1)):
            window.append(self.entries[j])
            j = self._step_from(j)
        self._prepared &= set(window)  # the ones left behind are dropped from the RAM disk below
        for p in window:
            if p not in self._prepared:
                view = p
                size = imginfo.size(p)
                if size and MAX_PIXELS and size[0] * size[1] > MAX_PIXELS and thumbs.available:
                    view = thumbs.shrunk(p) or p
                self._views[p] = view
                stage.put(view)
                self._prepared.add(p)
                self.inputs.flush()
                return
        stage.keep_only([self._views[p] for p in window if p in self._views])

    def _step_from(self, j):
        keep_sel, self.sel = self.sel, j
        try:
            return self._step(1)
        finally:
            self.sel = keep_sel

    def _jump(self, ch):
        """Select the next image (after the current one, wrapping) whose
        file name starts with the typed letter."""
        n = len(self.entries)
        for i in range(1, n + 1):
            j = (self.sel + i) % n
            if self.entries[j] not in SPECIAL and self.entries[j].rsplit("/", 1)[-1].lower().startswith(ch):
                self.sel = j
                return

    # ---- drawing -----------------------------------------------------
    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        if self.state == "search":
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

    def _special_tile(self, ctx, e, x, y, w, h):
        if e == SEARCH:
            rgb, label, sub = (0.1, 0.3, 0.6), "Search", self.query[:9] or "name"
        elif e == STORAGE:
            rgb, label = (0.5, 0.3, 0.1), "Storage"
            sub = "Flash" if self.folder == storage.KEPT else self.folder.split("/")[1][:9]
        elif e == SHOW:
            rgb, label, sub = (0.1, 0.45, 0.2), "Slides", "%d s" % self.seconds
        else:
            rgb, label, sub = (0.35, 0.35, 0.4), "Settings", LAYOUTS[self.layout_no][0][:9]
        ctx.rgb(*rgb).rectangle(x, y, w, h).fill()
        if w < 60:   # a small tile: one short word
            self._text(ctx, SHORT[e], x + w // 2, y + h // 2, 11)
            return
        k = 1 if h < 90 else 1.8   # the big focus tile gets bigger text
        self._text(ctx, label, x + w // 2, y + h // 2 - 7 * k, 13 * k)
        self._text(ctx, sub, x + w // 2, y + h // 2 + 9 * k, 11 * k, rgb=(0.85, 0.85, 0.85))

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
        if path in SPECIAL:
            self._special_tile(ctx, path, x, y, w, h)
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
        for idx, x, y, w, h in self.layout.tiles(self.sel, n):
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
        self._text(ctx, "Settings", 0, -85, 16, rgb=(0.8, 0.8, 0.9))
        vals = ("< %s >" % LAYOUTS[self.layout_no][0], "< %d s >" % self.seconds,
                "< %d px >" % keep.size, "%d kept" % keep.count())
        for i, name in enumerate(self.ROWS):
            y = -52 + i * 34
            if i == self._row:
                ctx.rgb(1, 1, 1)
                ctx.line_width = 2
                ctx.rectangle(-85, y - 15, 170, 32).stroke()
            self._text(ctx, name, 0, y - 5, 11, rgb=(0.7, 0.7, 0.7))
            self._text(ctx, vals[i], 0, y + 9, 14)
        self._text(ctx, "L/R change  OK clear", 0, 92, 11)

    def _measure(self, path):
        """Work out how to show a picture before decoding it: where it goes,
        or why it can't be shown. A picture over MAX_PIXELS is replaced by a
        shrunk copy when imgtool is there to make one."""
        self._shown = path
        self._rect = None
        self._note = None
        self._draw_path = path
        self._ram = None
        self._kept = keep.has(path)
        tried = None
        if self._small and self._small[0] == path:
            tried = self._small          # _background() has just had a go
        self._small = None
        size = imginfo.size(path)
        if size is None:
            self._note = ("Can't read", path.rsplit("/", 1)[-1])
            return
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

    def _draw_view(self, ctx):
        path = self.entries[self.sel]
        if path != self._shown:
            self._measure(path)
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
        if self._kept and self.state == "view":
            self._text(ctx, "kept", 0, -100, 11, bg=True, rgb=(1, 0.9, 0.3))
        if self.state == "show" and self._paused:
            self._text(ctx, "paused", 0, -100, 11, bg=True)


__app_export__ = GalleryApp
