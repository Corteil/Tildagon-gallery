class TouchScroller:
    """Turns a touch position into whole-image scroll steps.

    Feed update() once per frame with the finger position, or None when
    nothing is touching. Position can be anything that moves along the
    sensor in one direction (0..1 along a strip, an angle in degrees).

    step      distance the finger must travel for one image
    period    set to the full range (e.g. 360) if the sensor wraps around
    returns   +N / -N images to move this frame, 0 when idle
    """

    def __init__(self, step=0.1, period=None):
        self.step = step
        self.period = period
        self._anchor = None

    def _delta(self, pos):
        d = pos - self._anchor
        if self.period:
            half = self.period / 2
            if d > half:
                d -= self.period
            elif d < -half:
                d += self.period
        return d

    def update(self, pos):
        if pos is None:
            self._anchor = None
            return 0
        if self._anchor is None:
            self._anchor = pos
            return 0
        d = self._delta(pos)
        n = int(d / self.step)  # truncates toward zero
        if n:
            self._anchor += n * self.step
            if self.period:
                self._anchor %= self.period
        return n
