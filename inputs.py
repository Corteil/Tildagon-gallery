from math import pi, sin, cos, atan2

from system.eventbus import eventbus
from events.input import ButtonDownEvent, ButtonUpEvent, BUTTON_TYPES

# 2026 front board extras. Missing on the 2024 badge, so optional.
try:
    from events.joystick import JOYSTICK_BUTTON_TYPES
except ImportError:
    JOYSTICK_BUTTON_TYPES = {}
try:
    from frontboards.twentysix import TOUCH
except ImportError:
    TOUCH = {}

PADS = 12  # touch pads in the 2026 ring, TOUCH01..TOUCH12, clockwise
KEYS = ("UP", "DOWN", "LEFT", "RIGHT", "CONFIRM", "CANCEL")


def _has(kind, button):
    try:
        return kind in button
    except TypeError:
        return kind == button


class Inputs:
    """Collects badge input events for both the 2024 and 2026 badges.

    keys()            names pressed since last call, any of KEYS. The 2026
                      joystick maps onto the same names (SELECT = CONFIRM).
    touch_position()  finger position on the 2026 touch ring as 0..12 (pad
                      numbers, clockwise), or None when untouched or when
                      the badge has no touch pads.
    """

    def __init__(self):
        self._touched = set()
        self._queue = []
        self._bound = False
        self.bind()

    def bind(self):
        if not self._bound:
            eventbus.on(ButtonDownEvent, self._down, self)
            eventbus.on(ButtonUpEvent, self._up, self)
            self._bound = True

    def unbind(self):
        if self._bound:
            eventbus.remove(ButtonDownEvent, self._down, None)
            eventbus.remove(ButtonUpEvent, self._up, None)
            self._bound = False
            self._touched.clear()

    def _down(self, event):
        names = set()  # a set, so one press can't count twice
        for name in KEYS:
            if name in BUTTON_TYPES and _has(BUTTON_TYPES[name], event.button):
                names.add(name)
        for name in JOYSTICK_BUTTON_TYPES:
            if _has(JOYSTICK_BUTTON_TYPES[name], event.button):
                names.add("CONFIRM" if name == "SELECT" else name)
        self._queue.extend(names)
        for name in TOUCH:
            if _has(TOUCH[name], event.button):
                self._touched.add(int(name[5:]) - 1)

    def _up(self, event):
        for name in TOUCH:
            if _has(TOUCH[name], event.button):
                self._touched.discard(int(name[5:]) - 1)

    def keys(self):
        q = self._queue
        self._queue = []
        return q

    def touch_position(self):
        if not self._touched:
            return None
        sx = sy = 0.0
        for i in self._touched:
            a = i * 2 * pi / PADS
            sx += cos(a)
            sy += sin(a)
        if sx * sx + sy * sy < 1e-6:  # opposite pads cancel out
            return None
        return (atan2(sy, sx) % (2 * pi)) * PADS / (2 * pi)
