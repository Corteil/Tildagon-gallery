"""Where pictures come from: each mounted SD card plus the badge's own flash
(where up to MAX_KEEP resized pictures are kept, see keep.py). The HDMI
hexpansion and an SD hexpansion can't be fitted together, so the flash copy is
what lets the gallery run with HDMI.

    choices()            [(label, folder), ...]
    current()            the folder to open: the saved choice, else a sensible default
    save(folder=..., seconds=...)   remember a choice in flash
"""
import os

KEPT_ROOT = "/gallery"           # in the badge's flash
KEPT = KEPT_ROOT + "/kept"       # the kept pictures
SETTINGS = KEPT_ROOT + "/settings.txt"
PICTURES = "Pictures"            # folder looked for on each card


def _mkdirs():
    for d in (KEPT_ROOT, KEPT):
        try:
            os.mkdir(d)
        except OSError:
            pass


def sd_mounts():
    """Mount points of the SD cards that are there: /sdcard, /sdcard_1 ..."""
    try:
        names = os.listdir("/")
    except OSError:
        return []
    out = []
    for n in sorted(names):
        if n.startswith("sdcard"):
            try:
                os.listdir("/" + n)
            except OSError:
                continue
            out.append("/" + n)
    return out


def choices():
    out = [("SD " + m[1:], m + "/" + PICTURES) for m in sd_mounts()]
    out.append(("Flash (kept)", KEPT))
    return out


def load():
    d = {}
    try:
        with open(SETTINGS) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k:
                    d[k] = v
    except OSError:
        pass
    return d


def save(**kw):
    d = load()
    d.update(kw)
    _mkdirs()
    try:
        with open(SETTINGS, "w") as f:
            for k in d:
                f.write("%s=%s\n" % (k, d[k]))
    except OSError:
        pass  # flash not writable: the choice just isn't remembered


def _has_pictures(folder):
    from . import scanner
    return bool(scanner.list_images(folder))


def current():
    opts = [f for _, f in choices()]
    saved = load().get("folder")
    if saved in opts:
        return saved
    for f in opts:  # first card with pictures
        if f != KEPT and _has_pictures(f):
            return f
    if _has_pictures(KEPT):
        return KEPT
    return opts[0]
