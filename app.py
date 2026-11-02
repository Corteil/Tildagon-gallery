import app

from .layouts import LAYOUTS
from .inputs import Inputs, PADS
from .touch_scroll import TouchScroller
from . import imginfo
from . import scanner

ROOT = "/sdcard/Pictures"  # the SD card mounts at /sdcard; change to suit
LAYOUT = 0                 # index into LAYOUTS
TOUCH_STEP = 1.0           # pads of finger travel round the ring per image
# Pictures with more pixels than this are not drawn (the badge can run out of
# memory decoding them). 512 x 512 is a cautious starting point: find your
# badge's real limit with `tools/prepare.py --test-ladder`, then raise or
# lower this. 0 turns the check off.
MAX_PIXELS = 512 * 512


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
        self.files = scanner.list_images(ROOT)
        self.layout = LAYOUTS[LAYOUT][1]()
        self.sel = 0
        self.state = "browse"  # "browse" or "view"
        self._page = -1
        self._tiles = []       # (path, thumbnail path or None) for this page
        self._shown = None     # picture the viewer has measured
        self._rect = None      # where to draw it
        self._note = None      # lines to show instead, if it can't be drawn

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
            self._message(ctx, "No images in", ROOT)
        elif self.state == "browse":
            self._draw_browse(ctx)
        else:
            self._draw_view(ctx)
        ctx.restore()

    def _message(self, ctx, *lines):
        ctx.rgb(1, 1, 1)
        ctx.font_size = 14
        ctx.text_align = ctx.CENTER
        ctx.text_baseline = ctx.MIDDLE
        y = -9 * (len(lines) - 1)
        for line in lines:
            ctx.move_to(0, y).text(line[:22])
            y += 18

    def _load_page(self, page):
        per = self.layout.per_page
        self._tiles = []
        for path in self.files[page * per:(page + 1) * per]:
            t = scanner.thumb_path(path)
            self._tiles.append((path, t if scanner.exists(t) else None))
        self._page = page

    def _draw_browse(self, ctx):
        per = self.layout.per_page
        page = self.sel // per
        if page != self._page:
            self._load_page(page)
        for i, (path, thumb) in enumerate(self._tiles):
            x, y, w, h = self.layout.cells[i]
            if thumb:
                ctx.image(thumb, x, y, w, h)
            else:
                # no thumbnail: a colour from the name, and its first letter
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
        x, y, w, h = self.layout.cells[self.sel % per]
        ctx.rgb(1, 1, 1)
        ctx.line_width = 3
        ctx.rectangle(x, y, w, h).stroke()

    def _measure(self, path):
        """Work out how to show a picture before decoding it: where it goes,
        or why it can't be shown."""
        self._shown = path
        self._rect = None
        self._note = None
        size = imginfo.size(path)
        if size is None:
            self._note = ("Can't read", path.rsplit("/", 1)[-1])
        elif MAX_PIXELS and size[0] * size[1] > MAX_PIXELS:
            self._note = ("Too big", "%d x %d" % size, "limit %d px" % MAX_PIXELS)
        else:
            self._rect = _fit(size[0], size[1])

    def _draw_view(self, ctx):
        path = self.files[self.sel]
        if path != self._shown:
            self._measure(path)
        if self._rect:
            ctx.image(path, *self._rect)
        else:
            self._message(ctx, *self._note)


__app_export__ = GalleryApp
