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


def find_images(primary, fallbacks=()):
    """(folder, images) for the first of primary, then the fallbacks, that has
    pictures in it. If none has, (primary, [])."""
    for root in (primary,) + tuple(fallbacks):
        files = list_images(root)
        if files:
            return root, files
    return primary, []


def thumb_path(path):
    """Where an image's thumbnail is: a PNG in a hidden .thumbs folder next
    to it, named after the picture (pic.jpg -> .thumbs/pic.jpg.png). The
    tools/prepare.py script on a PC makes them."""
    d, _, name = path.rpartition("/")
    return "%s/.thumbs/%s.png" % (d, name)


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False
