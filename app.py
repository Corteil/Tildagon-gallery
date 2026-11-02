import app

from .layouts import LAYOUTS
from .inputs import Inputs, PADS
from .touch_scroll import TouchScroller
from . import scanner
from . import thumbs

ROOT = "/sdcard/Pictures"  # the SD card mounts at /sdcard; change to suit
THUMB_FRAMES = 3           # frames a tile stays drawn before it is captured
LAYOUT = 0             # index into LAYOUTS
TOUCH_STEP = 1.0       # pads of finger travel round the ring per image


class GalleryApp(app.App):
    def __init__(self):
        super().__init__()
        self.inputs = Inputs(self)
        self.scroller = TouchScroller(step=TOUCH_STEP, period=PADS)
        self.files = scanner.list_images(ROOT)
        self.layout = LAYOUTS[LAYOUT][1]()
        self.sel = 0
        self.state = "browse"  # "browse" or "view"
        self._page = -1
        self._tiles = []      # (path, thumbnail path or None) for this page
        self._todo = []       # tile numbers still needing a thumbnail
        self._job = None      # tile being captured now
        self._job_wait = 0
        self._bad = set()     # images a thumbnail couldn't be made for

    # ---- input -------------------------------------------------------
    def update(self, delta):
        self.inputs.bind()  # no-op unless we were unbound on minimise
        n = len(self.files)

        steps = self.scroller.update(self.inputs.touch_position())
        if steps and n:
            if self.state == "browse":
                self.sel = max(0, min(n - 1, self.sel + steps))
            else:
                self.sel = (self.sel + steps) % n

        for key in self.inputs.keys(delta):
            if key == "CANCEL":
                if self.state == "view":
                    self.state = "browse"
                else:
                    self.inputs.unbind()
                    self.minimise()
                    return
            elif not n:
                continue
            elif len(key) == 1:  # a letter on a USB keyboard
                self._jump(key)
            elif key in ("NEXT", "PREV"):
                self.sel = (self.sel + (1 if key == "NEXT" else -1)) % n
            elif self.state == "browse":
                if key == "CONFIRM":
                    self.state = "view"
                elif key in ("UP", "DOWN", "LEFT", "RIGHT"):
                    self.sel = self.layout.move(self.sel, key, n)
            else:
                # viewer: RIGHT/DOWN = next image, LEFT/UP = previous
                if key in ("RIGHT", "DOWN"):
                    self.sel = (self.sel + 1) % n
                elif key in ("LEFT", "UP"):
                    self.sel = (self.sel - 1) % n

        self._thumb_step()

    def _thumb_step(self):
        """Make the missing thumbnails of this page, one tile at a time. A tile
        is drawn at full quality in place, left for a few frames, then its
        pixels are read back from the screen. Needs display.get_framebuffer."""
        if self.state != "browse" or not thumbs.available():
            if self._job is not None:  # interrupted: try it again later
                self._todo.insert(0, self._job)
                self._job = None
            return
        if self._job is None:
            if self._todo and self._page >= 0:
                self._job = self._todo.pop(0)
                self._job_wait = 0
            return
        self._job_wait += 1
        if self._job_wait < THUMB_FRAMES:
            return
        i, self._job = self._job, None
        path = self._tiles[i][0]
        x, y, w, h = self.layout.cells[i]
        t = scanner.thumb_path(path, w)
        try:
            thumbs.capture(t, x + 120, y + 120, w, h)
            self._tiles[i] = (path, t)
        except Exception as e:
            print("Gallery: no thumbnail for", path, e)
            self._bad.add(path)

    def _jump(self, ch):
        """Select the next image (after the current one, wrapping) whose
        file name starts with the typed letter."""
        n = len(self.files)
        for i in range(1, n + 1):
            j = (self.sel + i) % n
            if self.files[j].rsplit("/", 1)[-1].lower().startswith(ch):
                self.sel = j
                return

    # ---- drawing -----------------------------------------------------
    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        if not self.files:
            self._message(ctx, "No images in " + ROOT)
        elif self.state == "browse":
            self._draw_browse(ctx)
        else:
            self._draw_view(ctx)
        ctx.restore()

    def _message(self, ctx, text):
        ctx.rgb(1, 1, 1)
        ctx.font_size = 14
        ctx.text_align = ctx.CENTER
        ctx.text_baseline = ctx.MIDDLE
        ctx.move_to(0, 0).text(text)

    def _load_page(self, page):
        per = self.layout.per_page
        self._tiles = []
        self._todo = []
        self._job = None
        for i, path in enumerate(self.files[page * per:(page + 1) * per]):
            t = scanner.thumb_path(path, self.layout.cells[i][2])
            have = scanner.exists(t)
            self._tiles.append((path, t if have else None))
            if not have and path not in self._bad:
                self._todo.append(i)
        self._page = page

    def _draw_browse(self, ctx):
        per = self.layout.per_page
        page = self.sel // per
        if page != self._page:
            self._load_page(page)
        for i, (path, thumb) in enumerate(self._tiles):
            x, y, w, h = self.layout.cells[i]
            if i == self._job:
                ctx.image(path, x, y, w, h)  # the picture itself, to be captured
            elif thumb:
                ctx.image(thumb, x, y, w, h)
            else:
                # placeholder: a colour from the name, and its first letter
                v = hash(path)
                ctx.rgb(0.15 + ((v >> 16) & 255) / 400,
                        0.15 + ((v >> 8) & 255) / 400,
                        0.15 + (v & 255) / 400).rectangle(x, y, w, h).fill()
                ctx.rgb(1, 1, 1)
                ctx.font_size = 20
                ctx.text_align = ctx.CENTER
                ctx.text_baseline = ctx.MIDDLE
                ctx.move_to(x + w // 2, y + h // 2).text(
                    path.rsplit("/", 1)[-1][:1].upper())
        sel = self.sel % per
        if sel != self._job:  # the outline would be captured into the thumbnail
            x, y, w, h = self.layout.cells[sel]
            ctx.rgb(1, 1, 1)
            ctx.line_width = 3
            ctx.rectangle(x, y, w, h).stroke()

    def _draw_view(self, ctx):
        # TODO: preserve aspect ratio, decode ahead, zoom/pan
        ctx.image(self.files[self.sel], -120, -120, 240, 240)


__app_export__ = GalleryApp
