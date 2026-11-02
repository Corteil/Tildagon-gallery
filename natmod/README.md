# imgtool: fast thumbnails and resizing, inside the app

Everything runs from the gallery app's own folder on the badge. Nothing goes
in `/lib`, and the firmware is not touched. Two files in the app folder do the
work:

* `imgtool.py`: the Python half (opens files, writes results)
* `_imgtool.mpy`: a **native module**: C code compiled to machine code and loaded
  at run time. It does the pixel work using three libraries by Larry Bank:
  [JPEGDEC](https://github.com/bitbank2/JPEGDEC),
  [PNGdec](https://github.com/bitbank2/PNGdec) and
  [JPEGENC](https://github.com/bitbank2/JPEGENC) (Apache 2.0).

```python
from . import imgtool            # from inside the app
imgtool.size("/sdcard/Pictures/a.jpg")                    # (4000, 3000)
imgtool.thumbnail("a.jpg", "a.png", 80)                   # centre-cropped square PNG
imgtool.resize("a.jpg", "a_small.jpg", 480, quality=85)   # longest side 480, JPEG
```

Errors: `ValueError` (not a readable JPEG/PNG), `NotImplementedError` (interlaced
or 16-bit PNG, some rare JPEGs), `MemoryError`, `OSError`. The app's
`thumbs.py` uses it when it loads and copes with all four; if `_imgtool.mpy`
doesn't suit the firmware, the app carries on without it.

## Installing

Install the gallery app as usual: `_imgtool.mpy` is in the app folder already
(the repo root). Check it suits your firmware (below); if it doesn't, build one
and `make install` puts it in the app folder.

The prebuilt `_imgtool.mpy` is for MicroPython 1.28.0 (commit e0e9fbb, what
badge-2024-software pins), mpy format 6.3, xtensawin. A native module is tied to
the exact MicroPython it was built against, so on the badge run
`import sys; print(sys.implementation._mpy, sys.implementation.version)`: you
want `11014 (1, 28, 0, '')`.

### If it does not fit, build it

It must be built from the **same MicroPython source as your firmware** (for
badge-2024-software: its `micropython` submodule). You need the ESP32
cross-compiler (`xtensa-esp-elf-gcc`, from ESP-IDF or Espressif's crosstool-NG
releases) and Python packages `pyelftools` and `ar`.

```sh
./fetch_libs.sh                      # the three bitbank2 libraries, at tested versions
make ARCH=xtensawin MPY_DIR=/path/to/micropython install   # builds, copies to the app folder
```

The Makefile and `mpy_ld_wrap.py` work around four problems you hit with Espressif's
current toolchain and MicroPython 1.28's `mpy_ld.py` (each cost a failed module on
a real badge, so don't remove them): the compiler defaults to a big-endian core
(`-mdynconfig=xtensa_esp32s3.so` fixes it), `mpy_ld` mixes up same-named sections
from different object files, read-only data must be 4-byte aligned, and
`&table[N]` pointers lose their offset. See the comments in those files.

MicroPython's makefile looks for `xtensa-esp32-elf-gcc`; Espressif's newer
toolchains call it `xtensa-esp-elf-gcc`, so make symlinks of the old names
(`xtensa-esp32-elf-gcc` -> `xtensa-esp-elf-gcc`, and the same for `ld`, `ar`,
`as`, `objcopy`, `objdump`, `nm`, `size`, `strip`, `readelf`) in a folder on `PATH`.

## How it is fast

* A JPEG is decoded at **1/2, 1/4 or 1/8 size** straight from the DCT, so a 12
  megapixel photo is only ever 500 x 375 in memory when making a thumbnail.
* A PNG is streamed a row at a time and averaged down as it arrives.
* Shrinking is an area average, so thumbnails are clean. EXIF rotation is
  applied, so portrait photos come out upright.
* The file is read in 4 KB chunks through Python's own file object, so a
  multi-megabyte photo is never held in memory.
* Memory comes from MicroPython's heap, which on the badge should be PSRAM (not
  checked). A 480 x 360 resize peaks at roughly 1 MB; a thumbnail much less.
* Thumbnails are written as uncompressed PNG (19 KB at 80 x 80): no compressor
  needed, and quick for the badge to draw.

While it runs, the badge's Python is blocked (one picture at a time), which is
why the app makes one thumbnail per frame.

## Testing on a PC

```sh
./fetch_libs.sh
cd test && make                       # host build of the C core, imgcli
python3 compare.py                    # output vs Pillow: formats, sizes, EXIF 1-8, bad files
python3 app_test.py                   # the gallery app using it, end to end
./asan.sh                             # AddressSanitizer + UBSan + leak check
```

And as a real native module in MicroPython's unix port (x64), which exercises
the loader and the Python callbacks:

```sh
cd /path/to/micropython/ports/unix && make FROZEN_MANIFEST= MICROPY_PY_BTREE=0 MICROPY_PY_FFI=0 MICROPY_PY_SSL=0
cd /path/to/Tildagon-gallery/natmod
make ARCH=x64 MPY_DIR=/path/to/micropython BUILD=build-x64
mkdir /tmp/lib && cp _imgtool.mpy ../imgtool.py /tmp/lib
MPHEAP=3M MPYLIB=/tmp/lib test/run_mp.sh /path/to/micropython/ports/unix/build-standard/micropython
```

## Known limits

* **Run on two badges** (`python3 tools/badge.py test`, both SELFTEST PASSED). Earlier note, now out of date: **Not run on a badge yet.** The ESP32-S3 `_imgtool.mpy` builds, and the same
  source passes every test as an x64 module on a PC, but nobody has loaded the
  Xtensa one on real hardware. Possible trouble: native code must fit in the
  firmware's executable RAM (it is 47 KB of code and 37 KB of read-only data),
  and the firmware's MicroPython must match the one it was built with.
* JPEG and PNG only. GIF and BMP are not handled here (the gallery's PC tool
  does those, and `ctx.image` still draws GIFs directly).
* Interlaced and 16-bit PNGs, arithmetic-coded and lossless JPEGs: reported as
  `NotImplementedError`. PNGs wider than about 4000 pixels are refused.
* JPEGDEC fails on some unusual but valid files. I found one synthetic 1600 x
  1200 gradient it cannot decode even from RAM; it is reported as `ValueError`
  and the app falls back. Real camera photos were not available to me; I only
  tried synthetic pictures.
* Pictures pass through RGB565 in the middle, so colours are within about 4
  levels (of 255) of Pillow's.
* Timings on the badge are unmeasured. On a PC a 12 MP JPEG -> 480 px takes
  about 15 ms; the badge will be far slower.
* The libraries' ESP32-S3 SIMD assembly is not used (it needs Arduino build
  flags): a possible later speed-up.
