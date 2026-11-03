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
from math import sin, cos, sqrt, pi, ceil


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
    """A honeycomb: one middle hexagon and 18 round it (two rings). Pictures keep
    their cells. The highlight moves from cell to cell (the way the arrow points);
    the middle one only changes when CONFIRM swaps the highlighted picture with it
    (CONFIRM on the middle one opens it). With more pictures than cells, moving off
    the edge scrolls the 18 outer cells to the next (or previous) page; the middle
    one stays."""
    shape = "hex"
    focus = False
    per_page = 1
    RING = 18
    # axial neighbours, clockwise on the screen from the right
    DIRS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))

    def __init__(self, r=25, gap=3):
        w = sqrt(3) * r
        dx = w + gap
        dy = 1.5 * r + gap * 0.87
        wd = 2 * ceil(w / 2)    # an even width, so the middle hexagon is exactly on the centre
        cells = [(0, 0)]
        for k in (1, 2):                      # the rings, each walked clockwise from the right
            q, rr = self.DIRS[0][0] * k, self.DIRS[0][1] * k
            for side in range(6):
                dq, dr = self.DIRS[(side + 2) % 6]
                for _ in range(k):
                    cells.append((q, rr))
                    q, rr = q + dq, rr + dr
        self.slots = []     # (x, y, w, h) of cell 0 (the middle), then the 18 round it
        self._mid = []      # centres of the same cells
        for q, rr in cells:
            cx, cy = dx * (q + rr / 2), dy * rr
            self.slots.append((int(round(cx - wd / 2)), int(round(cy - r)), wd, 2 * r))
            self._mid.append((cx, cy))
        self.cells = []     # picture in each cell: [middle, outer 0, outer 1, ...]
        self.page = 0

    def reset(self, n):
        """Start again with pictures 0..n-1 in order: picture 0 in the middle."""
        self.cells = list(range(n))
        self.page = 0

    def _sync(self, sel, n):
        if len(self.cells) != n:
            self.reset(n)
        if sel in self.cells:
            pos = self.cells.index(sel)
            if pos:
                self.page = (pos - 1) // self.RING
        return self.cells.index(sel) if sel in self.cells else None

    def _cell(self, slot, n):
        """The picture in a cell (0 = middle, 1..18 = outer) on this page, or None if it is empty."""
        pos = 0 if slot == 0 else 1 + self.page * self.RING + slot - 1
        return self.cells[pos] if pos < n else None

    def tiles(self, sel, n):
        if not n:
            return []
        self._sync(sel, n)
        out = []
        for slot in range(1 + self.RING):
            pic = self._cell(slot, n)
            if pic is not None:
                out.append((pic,) + self.slots[slot])
        return out

    @staticmethod
    def outline(x, y, w, h):
        """Corners of the hexagon (pointy top) that fills the box."""
        cx, cy, r = x + w / 2, y + h / 2, h / 2
        return [(cx + r * cos(pi / 6 + k * pi / 3), cy + r * sin(pi / 6 + k * pi / 3)) for k in range(6)]

    def swap(self, sel, n):
        """CONFIRM: swap the highlighted picture with the middle one. False if it is
        the middle one already (the app opens it)."""
        pos = self._sync(sel, n)
        if not pos:
            return False
        self.cells[0], self.cells[pos] = self.cells[pos], self.cells[0]
        return True

    def move(self, sel, d, n):
        if not n:
            return sel
        pos = self._sync(sel, n)
        slot = 0 if pos == 0 else (pos - 1) % self.RING + 1
        here = self._mid[slot]
        best, best_cost = None, None
        for s in range(1 + self.RING):
            if s == slot or self._cell(s, n) is None:
                continue
            ax = {"RIGHT": self._mid[s][0] - here[0], "LEFT": here[0] - self._mid[s][0],
                  "DOWN": self._mid[s][1] - here[1], "UP": here[1] - self._mid[s][1]}[d]
            side = abs(self._mid[s][1] - here[1]) if d in ("LEFT", "RIGHT") else abs(self._mid[s][0] - here[0])
            if ax > 4 and (best is None or ax + 2 * side < best_cost):
                best, best_cost = s, ax + 2 * side
        if best is not None:
            return self._cell(best, n)
        # nothing further that way: scroll the outer cells a page, keeping the highlight on the same cell
        pages = (n - 2) // self.RING + 1 if n > 1 else 1
        step = 1 if d in ("RIGHT", "DOWN") else -1
        page = self.page + step
        if slot == 0 or not 0 <= page < pages:
            return sel
        self.page = page
        for s in range(slot, 0, -1):             # the same cell, or the last one that has a picture
            pic = self._cell(s, n)
            if pic is not None:
                return pic
        self.page -= step
        return sel


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
