"""Mosaic layouts. A layout provides:

    shape           "rect" or "hex": how each tile is cut
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


class HoneycombLayout(GridLayout):
    """Hexagonal tiles in staggered rows, packed to fit the round screen."""
    shape = "hex"

    def __init__(self, rows=(3, 4, 3), r=33, gap=3):
        self.rows = rows
        self.per_page = sum(rows)
        w = sqrt(3) * r
        h = 2 * r
        dx = w + gap
        dy = 1.5 * r + gap * 0.87
        top = -dy * (len(rows) - 1) / 2
        self.cells = []
        self.row_of = []
        for ri, cnt in enumerate(rows):
            for ci in range(cnt):
                cx = (ci - (cnt - 1) / 2) * dx
                cy = top + ri * dy
                self.cells.append((int(cx - w / 2), int(cy - h / 2), int(w), int(h)))
                self.row_of.append(ri)

    @staticmethod
    def outline(x, y, w, h):
        """Corners of the hexagon (pointy top) that fills the box."""
        cx, cy, r = x + w / 2, y + h / 2, h / 2
        return [(cx + r * cos(pi / 6 + k * pi / 3), cy + r * sin(pi / 6 + k * pi / 3)) for k in range(6)]

    def move(self, sel, d, n):
        if d == "LEFT":
            return max(0, sel - 1)
        if d == "RIGHT":
            return min(n - 1, sel + 1)
        per = self.per_page
        base, i = sel // per * per, sel % per
        x, y = self.cells[i][0] + self.cells[i][2] / 2, self.cells[i][1]
        best, score = None, None
        for j, c in enumerate(self.cells):
            if base + j >= n or j == i:
                continue
            if (d == "UP" and c[1] < y - 1) or (d == "DOWN" and c[1] > y + 1):
                dist = abs(c[0] + c[2] / 2 - x) + abs(c[1] - y) * 3  # the next row first
                if score is None or dist < score:
                    best, score = j, dist
        if best is not None:
            return base + best
        # off the top or bottom of the page: the same column on the next page
        nb = base - per if d == "UP" else base + per
        if nb < 0 or nb >= n:
            return sel
        row = self.row_of[-1] if d == "UP" else 0
        cands = [j for j in range(per) if self.row_of[j] == row and nb + j < n]
        if not cands:
            return sel
        j = min(cands, key=lambda j: abs(self.cells[j][0] + self.cells[j][2] / 2 - x))
        return nb + j


class FocusRingLayout:
    """The selected picture big in the middle, its neighbours in a ring round it."""
    shape = "rect"
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
