import os

# What the badge's ctx.image() can draw (its stb_image is built for PNG, GIF and JPEG only: no BMP)
EXTS = (".jpg", ".jpeg", ".png", ".gif")


def list_images(root, sort="name"):
    """Image paths directly inside root. sort: "name" (not minding case),
    "newest" or "oldest" (by file date)."""
    try:
        names = os.listdir(root)
    except OSError:
        return []
    out = [root + "/" + n for n in sorted(names, key=lambda n: n.lower())
           if not n.startswith(".") and n.lower().endswith(EXTS)]
    if sort in ("newest", "oldest"):
        def stamp(p):
            try:
                return os.stat(p)[8]
            except OSError:
                return 0
        out.sort(key=stamp, reverse=(sort == "newest"))
    return out


def list_dirs(root):
    """Names of the folders directly inside root (not the hidden ones), sorted."""
    try:
        names = os.listdir(root)
    except OSError:
        return []
    out = []
    for n in sorted(names, key=lambda n: n.lower()):
        if n.startswith("."):
            continue
        try:
            if os.stat(root + "/" + n)[0] & 0x4000:
                out.append(root + "/" + n)
        except OSError:
            pass
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
