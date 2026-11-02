#!/usr/bin/env python3
"""Get pictures ready for the Tildagon gallery. Runs on a PC, needs Pillow.

    python prepare.py ~/Photos /path/to/sdcard/Pictures

For each picture in the first folder this writes, into the second:

  * a copy shrunk to fit within --max pixels on its longest side (never
    enlarged), turned the right way up using its camera rotation, with any
    transparency flattened onto black, saved as a baseline JPEG or a PNG
  * a square 80x80 thumbnail in .thumbs/<name>.png, which the gallery shows in
    its mosaic

Run it again after adding pictures: ones already done are skipped.

    python prepare.py --test-ladder /path/to/sdcard/Pictures

writes pictures of growing size (256 to 2048 pixels square) to find the
largest the badge can draw. See MAX_PIXELS in app.py.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

SRC_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff")
THUMB = 80
LADDER = (256, 384, 512, 768, 1024, 1536, 2048)


def load(path):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, (0, 0, 0))
        flat.paste(im, mask=im.getchannel("A"))
        return flat
    return im.convert("RGB")


def save(im, path, fmt, quality):
    if fmt == "jpg":
        # baseline (not progressive) and 4:2:0 are the most widely decodable
        im.save(path, "JPEG", quality=quality, optimize=True,
                progressive=False, subsampling="4:2:0")
    else:
        im.save(path, "PNG", optimize=True)


def thumb_file(dst, outname):
    return os.path.join(dst, ".thumbs", outname + ".png")


def save_thumb(im, dst, outname):
    os.makedirs(os.path.join(dst, ".thumbs"), exist_ok=True)
    ImageOps.fit(im, (THUMB, THUMB), Image.LANCZOS).save(thumb_file(dst, outname), "PNG", optimize=True)


def prepare(src, dst, max_side, fmt, quality, force):
    if os.path.realpath(src) == os.path.realpath(dst):
        sys.exit("The two folders must differ: the originals are never changed.")
    os.makedirs(dst, exist_ok=True)
    made = skipped = failed = 0
    used = set()
    for name in sorted(os.listdir(src)):
        stem, ext = os.path.splitext(name)
        path = os.path.join(src, name)
        if name.startswith(".") or ext.lower() not in SRC_EXTS or not os.path.isfile(path):
            continue
        outname = stem + "." + fmt
        if outname.lower() in used:  # a.jpg and a.png in one folder
            outname = "%s-%s.%s" % (stem, ext.lower().lstrip("."), fmt)
        used.add(outname.lower())
        out = os.path.join(dst, outname)
        if (not force and os.path.exists(out) and os.path.exists(thumb_file(dst, outname))
                and os.path.getmtime(out) >= os.path.getmtime(path)):
            skipped += 1
            continue
        try:
            im = load(path)
            before = im.size
            im.thumbnail((max_side, max_side), Image.LANCZOS)  # shrinks only
            save(im, out, fmt, quality)
            save_thumb(im, dst, outname)
        except Exception as e:  # a broken file shouldn't stop the rest
            print("FAILED  %s: %s" % (name, e))
            failed += 1
            continue
        made += 1
        print("%-32s %dx%d -> %dx%d, %d KB" % (name, before[0], before[1], im.width, im.height,
                                              (os.path.getsize(out) + 1023) // 1024))
    print("%d made, %d already done, %d failed" % (made, skipped, failed))
    return failed == 0


def test_ladder(dst, fmt, quality):
    """Pictures of growing size, of noisy content (so they decode like a
    photo and don't compress away to nothing), each labelled with its size."""
    os.makedirs(dst, exist_ok=True)
    for s in LADDER:
        noise = Image.frombytes("RGB", (64, 64), os.urandom(64 * 64 * 3)).resize((s, s), Image.BICUBIC)
        draw = ImageDraw.Draw(noise)
        try:
            font = ImageFont.load_default(size=s // 4)
        except TypeError:  # old Pillow: fixed-size font
            font = ImageFont.load_default()
        draw.text((s // 2, s // 2), str(s), fill=(255, 255, 255), anchor="mm", font=font,
                  stroke_width=max(2, s // 80), stroke_fill=(0, 0, 0))
        outname = "test_%04d.%s" % (s, fmt)
        out = os.path.join(dst, outname)
        save(noise, out, fmt, quality)
        save_thumb(noise, dst, outname)
        print("%-16s %dx%d = %d pixels, %d KB" % (outname, s, s, s * s, (os.path.getsize(out) + 1023) // 1024))
    print("\nCopy these to the SD card, set MAX_PIXELS = 0 in app.py, and open each one.\n"
          "The largest that draws quickly is the badge's limit: set MAX_PIXELS to its\n"
          "pixel count, and use --max with its side length here. Delete test_*.* after.")


def main():
    ap = argparse.ArgumentParser(description="Resize pictures and make thumbnails for the Tildagon gallery.")
    ap.add_argument("folders", nargs="*", metavar="FOLDER",
                    help="the folder of original pictures, then the folder to write to "
                         "(Pictures on the SD card); with --test-ladder just the second one")
    ap.add_argument("--max", type=int, default=480, metavar="PX",
                    help="longest side in pixels (default 480: twice the screen, with room to zoom)")
    ap.add_argument("--format", choices=("jpg", "png"), default="jpg", help="output format (default jpg)")
    ap.add_argument("--quality", type=int, default=85, help="JPEG quality (default 85)")
    ap.add_argument("--force", action="store_true", help="redo pictures already done")
    ap.add_argument("--test-ladder", action="store_true",
                    help="write test pictures of growing size instead of converting any")
    a = ap.parse_args()
    if a.test_ladder:
        if len(a.folders) != 1:
            ap.error("--test-ladder takes one folder: where to write the test pictures")
        test_ladder(a.folders[0], a.format, a.quality)
        return
    if len(a.folders) != 2:
        ap.error("give the folder of pictures, then the folder to write to")
    sys.exit(0 if prepare(a.folders[0], a.folders[1], a.max, a.format, a.quality, a.force) else 1)


if __name__ == "__main__":
    main()
