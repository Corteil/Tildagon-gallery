import app

from .layouts import LAYOUTS
from .inputs import Inputs, PADS
from .touch_scroll import TouchScroller
from . import scanner

ROOT = "/sd/Pictures"  # change to wherever your external storage mounts
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
        self._tiles = []

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

        for key in self.inputs.keys():
            if key == "CANCEL":
                if self.state == "view":
                    self.state = "browse"
                else:
                    self.inputs.unbind()
                    self.minimise()
                    return
            elif not n:
                continue
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
                # placeholder until thumbnails are generated
                v = hash(path)
                ctx.rgb(0.15 + ((v >> 16) & 255) / 400,
                        0.15 + ((v >> 8) & 255) / 400,
                        0.15 + (v & 255) / 400).rectangle(x, y, w, h).fill()
        x, y, w, h = self.layout.cells[self.sel % per]
        ctx.rgb(1, 1, 1)
        ctx.line_width = 3
        ctx.rectangle(x, y, w, h).stroke()

    def _draw_view(self, ctx):
        # TODO: preserve aspect ratio, decode ahead, zoom/pan
        ctx.image(self.files[self.sel], -120, -120, 240, 240)


__app_export__ = GalleryApp
