#!/bin/sh
# usage: run_mp.sh /path/to/micropython   (the unix port built with imgtool)
set -e
here=$(cd "$(dirname "$0")" && pwd)
d=$(mktemp -d)
python3 - "$d" <<'PY'
import sys
from PIL import Image
sys.path.insert(0, ".")
d = sys.argv[1]
im = Image.new("RGB", (1600, 1200))
px = im.load()
for y in range(1200):
    for x in range(1600):
        px[x, y] = (x * 255 // 1600, y * 255 // 1200, (x + y) * 255 // 2800)
im.save(d + "/big.jpg", quality=90); im.resize((800, 600)).save(d + "/p.png")
open(d + "/bad.bin", "wb").write(b"not an image" * 20)
PY
convert "$d/p.png" -interlace PNG "$d/il.png"
"$1" "$here/mp_test.py" "$d"
python3 - "$d" <<'PY'
import sys
from PIL import Image
d = sys.argv[1]
for f, size, fmt in (("out_t.png", (80, 80), "PNG"), ("out_t40.png", (40, 40), "PNG"), ("out_r.jpg", (300, 225), "JPEG"), ("out_rp.jpg", (200, 150), "JPEG")):
    im = Image.open(d + "/" + f); im.load()
    assert im.size == size and im.format == fmt, (f, im.size, im.format)
print("outputs verified with Pillow")
PY
rm -rf "$d"
