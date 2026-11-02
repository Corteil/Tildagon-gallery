import os

EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
THUMB_DIR = "/sd/.thumbs"


def list_images(root):
    """Sorted list of image paths directly inside root (no recursion yet)."""
    try:
        names = os.listdir(root)
    except OSError:
        return []
    out = []
    for n in sorted(names):
        if n.startswith("."):
            continue
        if n.lower().endswith(EXTS):
            out.append(root + "/" + n)
    return out


def thumb_path(path):
    """Where the cached thumbnail for an image lives (not generated yet)."""
    return "{}/{:06x}.png".format(THUMB_DIR, hash(path) & 0xFFFFFF)


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False
