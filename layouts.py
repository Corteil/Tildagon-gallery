"""Mosaic layouts. A layout provides:

    per_page        tiles shown per page
    cells           list of (x, y, w, h) in ctx coords (origin at centre)
    move(sel, d, n) new selection index after pressing direction d
                    ("UP", "DOWN", "LEFT", "RIGHT"), n = number of images

Honeycomb and focus-ring layouts only need to provide the same three things,
so they can be added to LAYOUTS later without touching the app.
"""


class GridLayout:
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

    def move(self, sel, d, n):
        step = {"LEFT": -1, "RIGHT": 1, "UP": -self.cols, "DOWN": self.cols}[d]
        new = sel + step
        if new < 0 or new >= n:
            return sel
        return new


# (name, factory). 4x4 comes free from the same class.
LAYOUTS = (
    ("3x3 grid", lambda: GridLayout(3, 3)),
    ("4x4 grid", lambda: GridLayout(4, 4)),
)
