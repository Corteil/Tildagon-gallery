"""A second screen on the HDMI hexpansion.

Normally the hexpansion mirrors the badge's own screen. With a firmware that has
`display.Screen` (hazanjon's feature/hdmi-mirror, see his display_manager app),
an app can instead draw on a second, independent 240 x 240 screen with its own
ctx, and that goes to the TV while the badge's screen shows something else.

    s = SecondScreen()
    s.start()           # takes the port from the mirror, False if there is none
    ctx = s.ctx()       # draw on it like any ctx (origin in the middle)
    s.show(ctx)         # send the frame
    s.stop()            # give the port back to the mirror

The hexpansion holds the last frame it was sent, so a still stays up with no
further work.
"""
try:
    import display
except ImportError:  # not on a badge
    display = None

SIZE = 240
DRIVER = {"header": b"TDHD", "baudrate": 10_000_000}  # what the mirror uses too


def find_port():
    """The hexpansion port that is mirroring right now (the HDMI one), or None."""
    if display is None:
        return None
    for port in range(1, 7):
        try:
            if display.is_mirror_active(port):
                return port
        except Exception:
            pass
    return None


class SecondScreen:
    def __init__(self):
        self.port = None
        self.screen = None
        self.error = None

    @property
    def active(self):
        return self.screen is not None

    def start(self):
        """True once the second screen is up. Otherwise self.error says why."""
        if self.screen is not None:
            return True
        if display is None or not hasattr(display, "Screen"):
            self.error = "Needs the HDMI firmware"
            return False
        port = find_port()
        if port is None:
            self.error = "No HDMI mirror found"
            return False
        try:
            display.detach_mirror(port)
            self.screen = display.Screen(port=port, width=SIZE, height=SIZE,
                                         baudrate=DRIVER["baudrate"], driver=DRIVER)
            self.port = port
        except Exception as e:
            self.screen = None
            self.error = "HDMI: " + type(e).__name__
            print("gallery: second screen failed:", repr(e))
            self._attach(port)
            return False
        return True

    def ctx(self):
        return self.screen.get_ctx()

    def show(self, ctx):
        self.screen.end_frame(ctx)

    def stop(self):
        """Give the port back to the mirror. Safe to call when not started."""
        if self.screen is None:
            return
        try:
            self.screen.deinit()
        except Exception as e:
            print("gallery: second screen deinit failed:", repr(e))
        self.screen = None
        self._attach(self.port)

    @staticmethod
    def _attach(port):
        try:
            display.attach_mirror(port=port, baudrate=DRIVER["baudrate"], driver=DRIVER)
        except Exception as e:
            print("gallery: mirror re-attach failed:", repr(e))
