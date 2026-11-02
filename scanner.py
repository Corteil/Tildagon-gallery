import os

EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")


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


def thumb_path(path, size):
    """Where the size x size thumbnail for an image is cached: a hidden
    .thumbs folder next to it. The name comes from the file's name, size and
    modified time, so a replaced picture gets a new thumbnail."""
    d, _, name = path.rpartition("/")
    try:
        st = os.stat(path)
        key = "%s|%d|%d" % (name, st[6], st[8])
    except OSError:
        key = name
    h = 5381
    for c in key:
        h = (h * 33 + ord(c)) & 0xFFFFFF
    return "%s/.thumbs/%06x_%d.png" % (d, h, size)


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False
