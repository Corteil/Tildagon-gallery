"""Mosaic layouts. A layout provides:

    shape           "rect", "hex" or "circle": how each tile is cut
    tiles(sel, n)   what to draw when picture sel (of n) is selected: a list of
                    (index, x, y, w, h) in ctx coords (origin at the centre);
                    the tile for index sel gets the selection outline
    move(sel, d, n) new selection index after pressing direction d
                    ("UP", "DOWN", "LEFT", "RIGHT"), n = number of tiles
    focus           True if the selected tile is drawn big (see FocusRing)

Add a layout by adding it to LAYOUTS: the app needs nothing else.
"""
from math import sin, cos, sqrt, pi


class GridLayout:
    shape = "rect"
    focus = False

    def __init__(self, cols=3, rows=3, gap=3, span=240):
        self.cols = cols
        self.rows = rows
        self.per_page = cols * rows
        w = (span - gap * (cols - 1)) // cols
        half = span // 2
        self.cells = []
        for r in range(rows):
            for c in range(cols):
                self.cells.append((-half + c * (w + gap), -half + r * (w + gap), w, w))

    def tiles(self, sel, n):
        base = sel // self.per_page * self.per_page
        return [(base + i,) + self.cells[i] for i in range(min(self.per_page, n - base))]

    def move(self, sel, d, n):
        step = {"LEFT": -1, "RIGHT": 1, "UP": -self.cols, "DOWN": self.cols}[d]
        new = sel + step
        if new < 0 or new >= n:
            return sel
        return new


class HoneycombLayout:
    """A honeycomb built round the selected picture, which sits in the middle:
    19 hexagons (it and two rings). The pictures run along rows of ROW, so
    LEFT/RIGHT go one picture and UP/DOWN a row; the honeycomb moves, the
    selection stays in the middle."""
    shape = "hex"
    focus = False
    per_page = 1
    ROW = 6

    def __init__(self, r=26, gap=3):
        w = sqrt(3) * r
        dx = w + gap
        dy = 1.5 * r + gap * 0.87
        self.slots = []     # (picture offset, x, y, w, h), middle first
        for dr in (0, -1, 1, -2, 2):
            for dq in range(-2, 3):
                if abs(dq + dr) <= 2:
                    cx, cy = dx * (dq + dr / 2), dy * dr
                    self.slots.append((dq + self.ROW * dr, int(cx - w / 2), int(cy - r), int(w), int(2 * r)))
        self.slots.sort(key=lambda t: t[0] != 0)   # the middle one first (drawn first, so nothing hides it)

    def tiles(self, sel, n):
        return [(sel + o, x, y, w, h) for o, x, y, w, h in self.slots if 0 <= sel + o < n]

    @staticmethod
    def outline(x, y, w, h):
        """Corners of the hexagon (pointy top) that fills the box."""
        cx, cy, r = x + w / 2, y + h / 2, h / 2
        return [(cx + r * cos(pi / 6 + k * pi / 3), cy + r * sin(pi / 6 + k * pi / 3)) for k in range(6)]

    def move(self, sel, d, n):
        new = sel + {"LEFT": -1, "RIGHT": 1, "UP": -self.ROW, "DOWN": self.ROW}[d]
        return new if 0 <= new < n else sel


class FocusRingLayout:
    """The selected picture big in the middle, its neighbours in a ring round it; all round."""
    shape = "circle"
    focus = True
    per_page = 1

    def __init__(self, big=104, small=40, radius=88):
        self.big, self.small, self.radius = big, small, radius

    def tiles(self, sel, n):
        out = []
        r, s = self.radius, self.small
        for k in range(8):
            off = k + 1 if k < 4 else k - 8   # +1..+4 down the right, -4..-1 up the left
            idx = sel + off
            if 0 <= idx < n:
                a = (22.5 + 45 * k) * pi / 180
                out.append((idx, int(r * sin(a) - s / 2), int(-r * cos(a) - s / 2), s, s))
        b = self.big
        out.append((sel, -b // 2, -b // 2, b, b))   # last, so it is drawn on top
        return out

    def move(self, sel, d, n):
        return max(0, min(n - 1, sel + (-1 if d in ("LEFT", "UP") else 1)))


# (name, factory)
LAYOUTS = (
    ("3x3 grid", lambda: GridLayout(3, 3)),
    ("4x4 grid", lambda: GridLayout(4, 4)),
    ("Honeycomb", lambda: HoneycombLayout()),
    ("Focus ring", lambda: FocusRingLayout()),
)
