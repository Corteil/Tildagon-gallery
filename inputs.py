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
try:
    from events.keyboard import KEYBOARD_BUTTONS
except ImportError:
    KEYBOARD_BUTTONS = {}

PADS = 12  # touch pads in the 2026 ring, TOUCH01..TOUCH12, clockwise
KEYS = ("UP", "DOWN", "LEFT", "RIGHT", "CONFIRM", "CANCEL")
ARROWS = ("UP", "DOWN", "LEFT", "RIGHT")  # these repeat while held
HOLD_MS = 400    # held this long before repeating starts
REPEAT_MS = 70   # then one repeat per this many ms
# USB keyboard keys beyond arrows/Enter/Escape (those arrive as the six keys)
KEYBOARD_EXTRA = (("SPACE", "NEXT"), ("BACKSPACE", "PREV"))
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _has(kind, button):
    try:
        return kind in button
    except TypeError:
        return kind == button


def _add(names, name):
    if name not in names:
        names.append(name)


class Inputs:
    """Input for both the 2024 and 2026 badges.

    owner             the App. Button events only reach the focused app, so
                      handlers are registered against it, not a stand-in.
    keys(delta)       names pressed since the last call (delta = ms since the
                      last call, drives hold-to-repeat). Any of:
                        KEYS                  UP DOWN LEFT RIGHT CONFIRM CANCEL
                        "NEXT" / "PREV"       USB keyboard Space / Backspace
                        "a".."z"              a letter typed on a USB keyboard
                      The 2026 joystick maps onto KEYS (SELECT is CONFIRM) and
                      a press seen twice only counts once.
    touch_position()  finger position on the 2026 touch ring as 0..12 (pad
                      numbers, clockwise), or None when untouched or when
                      the badge has no touch pads.
    """

    def __init__(self, owner):
        self._owner = owner
        self._buttons = Buttons(owner)
        self._touched = set()
        self._queue = []
        self._held = {}
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

    def keys(self, delta=0):
        names = []  # in the order pressed, each once, so frames behave the same every run
        for n in self._queue:
            if n not in names:
                names.append(n)
        self._queue = []
        b = self._buttons
        for name in KEYS:
            t = BUTTON_TYPES[name]
            if b.pressed(t):
                _add(names, name)
                self._held[name] = 0
            elif name in ARROWS:
                if b.get(t):
                    h = self._held.get(name, 0) + delta
                    if h >= HOLD_MS:
                        h -= REPEAT_MS
                        _add(names, name)
                    self._held[name] = h
                else:
                    self._held[name] = 0
        if KEYBOARD_BUTTONS:
            for key, name in KEYBOARD_EXTRA:
                t = KEYBOARD_BUTTONS.get(key)
                if t is not None and b.pressed(t):
                    _add(names, name)
            for ch in LETTERS:
                t = KEYBOARD_BUTTONS.get(ch.upper())
                if t is not None and b.pressed(t):
                    _add(names, ch)
        return names

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
