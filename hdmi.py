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

The hexpansion does NOT hold a still: its firmware (testcard/src/main.c,
IDLE_AFTER_MS) shows "no signal" static when no row has arrived for 500 ms. So
keepalive(delta) must be called every frame; it resends the same frame (just a
retransmit of the screen's buffer, no drawing; get_ctx() and end_frame() are
always called as a pair, as the firmware expects) every KEEPALIVE_MS.
"""
try:
    import display
except ImportError:  # not on a badge
    display = None

SIZE = 240
DRIVER = {"header": b"TDHD", "baudrate": 10_000_000}  # what the mirror uses too
KEEPALIVE_MS = 350   # resend the frame at least this often; the hexpansion shows static after 500 ms of silence
REFRESH_AFTER_MS = 100   # refresh() does nothing if a frame went less than this long ago


HDMI_VID, HDMI_PID = 0x1969, 0x4544   # what the HDMI hexpansion's EEPROM says it is


def find_slot():
    """The port the HDMI hexpansion is plugged into, from the badge's own list of hexpansions, or None."""
    try:
        from system.hexpansion.util import get_slots_by_vid_pid
        slots = get_slots_by_vid_pid(HDMI_VID, HDMI_PID)
        return slots[0] if slots else None
    except Exception:
        return None


def find_port():
    """The port of the HDMI hexpansion: the one that is mirroring right now, else
    the one the badge found by its EEPROM id, or None."""
    if display is None:
        return None
    for port in range(1, 7):
        try:
            if display.is_mirror_active(port):
                return port
        except Exception:
            pass
    return find_slot()


def mirroring(port):
    try:
        return bool(display.is_mirror_active(port))
    except Exception:
        return False


class SecondScreen:
    def __init__(self):
        self.port = None
        self.screen = None
        self.error = None
        self._ctx = None       # the last frame sent
        self._quiet = 0        # ms since a frame was last sent

    @property
    def active(self):
        return self.screen is not None

    def switch_on(self):
        """Start the badge mirroring to the HDMI hexpansion if it is not already,
        like the HDMI Manager app does. True if the hexpansion is there and mirroring."""
        if display is None or not hasattr(display, "attach_mirror"):
            self.error = "Needs the HDMI firmware"
            return False
        port = find_port()
        if port is None:
            self.error = "No HDMI hexpansion found"
            return False
        if self.screen is None and not mirroring(port):
            try:
                display.attach_mirror(port=port, baudrate=DRIVER["baudrate"], driver=DRIVER)
            except Exception as e:
                self.error = "HDMI: " + type(e).__name__
                print("gallery: mirror attach failed:", repr(e))
                return False
        return True

    def start(self):
        """True once the second screen is up. Otherwise self.error says why."""
        if self.screen is not None:
            return True
        if display is None or not hasattr(display, "Screen"):
            self.error = "Needs the HDMI firmware"
            return False
        port = find_port()
        if port is None:
            self.error = "No HDMI hexpansion found"
            return False
        try:
            if mirroring(port):
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
        self._ctx = ctx
        self._quiet = 0

    def refresh(self):
        """Send the last frame now: call it just before something slow, so the
        silence the hexpansion sees starts from this moment. (Not if one went a moment ago.)"""
        if self.screen is None or self._ctx is None or self._quiet < REFRESH_AFTER_MS:
            return False
        return self._send()

    def keepalive(self, delta):
        """Call every frame with the ms since the last call. Sends the last frame
        again unless the next frame (guessed to take as long as this one) would still
        arrive within KEEPALIVE_MS, so the hexpansion never shows static even when
        frames are slow. True if it sent."""
        if self.screen is None or self._ctx is None:
            return False
        self._quiet += delta
        if self._quiet + delta < KEEPALIVE_MS:
            return False
        return self._send()

    def _send(self):
        try:
            # get_ctx() saves the drawing state and end_frame() restores it, so they go
            # in pairs; the pixels already in the screen's buffer are sent as they are
            self.screen.end_frame(self.screen.get_ctx())
        except Exception as e:
            print("gallery: HDMI keepalive failed:", repr(e))
            return False
        self._quiet = 0
        return True

    def stop(self):
        """Give the port back to the mirror. Safe to call when not started."""
        if self.screen is None:
            return
        try:
            self.screen.deinit()
        except Exception as e:
            print("gallery: second screen deinit failed:", repr(e))
        self.screen = None
        self._ctx = None
        self._attach(self.port)

    @staticmethod
    def _attach(port):
        try:
            display.attach_mirror(port=port, baudrate=DRIVER["baudrate"], driver=DRIVER)
        except Exception as e:
            print("gallery: mirror re-attach failed:", repr(e))
