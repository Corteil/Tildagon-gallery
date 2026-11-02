from math import pi, sin, cos, atan2

from system.eventbus import eventbus
from events.input import Buttons, BUTTON_TYPES, ButtonDownEvent, ButtonUpEvent

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
    """Input for both the 2024 and 2026 badges.

    owner             the App. Button events only reach the focused app, so
                      handlers are registered against it, not a stand-in.
    keys()            names pressed since the last call, any of KEYS. The
                      2026 joystick maps onto the same names (SELECT is
                      CONFIRM) and a press seen twice only counts once.
    touch_position()  finger position on the 2026 touch ring as 0..12 (pad
                      numbers, clockwise), or None when untouched or when
                      the badge has no touch pads.
    """

    def __init__(self, owner):
        self._owner = owner
        self._buttons = Buttons(owner)
        self._touched = set()
        self._queue = []
        self._bound = False
        self.bind()

    def bind(self):
        # The six standard keys come from Buttons. Events are only needed
        # for the 2026 joystick and touch ring.
        if not self._bound and (JOYSTICK_BUTTON_TYPES or TOUCH):
            eventbus.on(ButtonDownEvent, self._down, self._owner)
            eventbus.on(ButtonUpEvent, self._up, self._owner)
            self._bound = True

    def unbind(self):
        if self._bound:
            eventbus.remove(ButtonDownEvent, self._down, self._owner)
            eventbus.remove(ButtonUpEvent, self._up, self._owner)
            self._bound = False
        self._touched.clear()

    def _down(self, event):
        for name in JOYSTICK_BUTTON_TYPES:
            if _has(JOYSTICK_BUTTON_TYPES[name], event.button):
                self._queue.append("CONFIRM" if name == "SELECT" else name)
        for name in TOUCH:
            if _has(TOUCH[name], event.button):
                self._touched.add(int(name[5:]) - 1)

    def _up(self, event):
        for name in TOUCH:
            if _has(TOUCH[name], event.button):
                self._touched.discard(int(name[5:]) - 1)

    def keys(self):
        names = set(self._queue)  # a set, so one press can't count twice
        self._queue = []
        for name in KEYS:
            if self._buttons.pressed(BUTTON_TYPES[name]):
                names.add(name)
        return list(names)

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
