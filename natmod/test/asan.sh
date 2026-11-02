#!/bin/sh
# Build the core with AddressSanitizer/UBSan/LeakSanitizer and run it over a
# spread of pictures and sizes (odd sizes, rotated, truncated and junk files).
# usage: asan.sh [LIBS]   LIBS defaults to ../libs
set -e
here=$(cd "$(dirname "$0")" && pwd)
LIBS=${1:-$here/../libs}
J=$LIBS/jpegdec/src; E=$LIBS/jpegenc/src; P=$LIBS/pngdec/src
out=$(mktemp -d); S="-fsanitize=address,undefined -fno-sanitize=alignment,shift"
cd "$out"
gcc -g $S -w -DNO_SIMD -DPNG_MAX_BUFFERED_PIXELS=16386 -I"$here/../shim" -I$J -I$E -I$P -I"$here/.." -o imgcli_asan \
    "$here/imgcli.c" "$here/hostalloc.c" "$here/../core.c" "$here/../lib_jpegdec.c" "$here/../lib_jpegenc.c" "$here/../lib_pngdec.c" \
    $P/adler32.c $P/crc32.c $P/infback.c $P/inffast.c $P/inflate.c $P/inftrees.c $P/zutil.c
python3 - "$out" <<'PY'
import os, subprocess, sys
from PIL import Image
out = sys.argv[1]; cli = out + "/imgcli_asan"; d = out + "/in"; os.mkdir(d)
def pic(w, h):
    im = Image.new("RGB", (w, h)); px = im.load()
    for y in range(h):
        for x in range(w): px[x, y] = (x * 255 // w, y * 255 // h, (x + y) * 255 // (w + h))
    return im
for w, h in ((900, 700), (17, 15), (1, 1), (33, 47), (100, 101), (479, 359), (480, 368), (64, 48)):
    im = pic(w, h); im.save("%s/%dx%d.png" % (d, w, h)); im.convert("RGBA").save("%s/%dx%d_a.png" % (d, w, h))
    im.save("%s/%dx%d.jpg" % (d, w, h), quality=90)
    for o in (1, 3, 6, 8):
        ex = Image.Exif(); ex[0x0112] = o; im.save("%s/%dx%d_o%d.jpg" % (d, w, h, o), exif=ex)
good = open(d + "/900x700.jpg", "rb").read(); png = open(d + "/900x700.png", "rb").read()
open(d + "/trunc.jpg", "wb").write(good[:5000]); open(d + "/trunc.png", "wb").write(png[:5000])
open(d + "/junk.bin", "wb").write(os.urandom(300))
bad = n = 0
for f in sorted(os.listdir(d)):
    for mode, sz in (("thumb", 80), ("fit", 480), ("fit", 100), ("fit", 4000), ("thumb", 1), ("fit", 7), ("thumb", 33)):
        r = subprocess.run([cli, mode, str(sz), d + "/" + f, out + "/o.bin"], capture_output=True, text=True)
        n += 1
        if r.stderr.strip():
            bad += 1; print(f, mode, sz, r.stderr[:300])
print(n, "runs; with findings:", bad)
sys.exit(1 if bad else 0)
PY
rm -rf "$out"
