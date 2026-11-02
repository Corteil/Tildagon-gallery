# imgtool: fast thumbnails and resizing for the badge

A small native MicroPython module that shrinks JPEG and PNG pictures in C++, so
the gallery can make its own thumbnails and shrink big pictures on the badge
instead of needing a PC. It is built on three libraries by Larry Bank
(bitbank2, Apache 2.0): **JPEGDEC**, **PNGdec** and **JPEGENC**.

```python
import imgtool
imgtool.size("/sdcard/Pictures/a.jpg")                    # (4000, 3000)
imgtool.thumbnail("a.jpg", "a.png", 80)                   # centre-cropped square PNG
imgtool.resize("a.jpg", "a_small.jpg", 480, quality=85)   # whole picture, longest side 480
```

Errors: `ValueError` (not a readable JPEG/PNG), `NotImplementedError` (interlaced
or 16-bit PNG, some rare JPEGs), `MemoryError`, `OSError`. The gallery's
`thumbs.py` catches all four and falls back to the PC tool's output.

## How it is fast

* A JPEG is decoded at **1/2, 1/4 or 1/8 size** straight from the DCT, so a 12
  megapixel photo is only ever 500 x 375 in memory when making a thumbnail.
* PNGs are streamed a row at a time and averaged down as they arrive.
* Pixel buffers and the output go in **PSRAM** (`heap_caps_malloc` with
  `MALLOC_CAP_SPIRAM`); the decoder state (hot, 20-60 KB) goes in internal RAM
  when it fits, PSRAM otherwise.
* Shrinking is an area average, not nearest-neighbour, so thumbnails are clean.
* EXIF rotation is applied, so portrait photos come out upright.
* Thumbnails are written as uncompressed PNG (19 KB each at 80 x 80), which
  needs no compressor and which the badge's `ctx.image` reads quickly.

While it runs the badge's Python is blocked (one picture, typically well under a
second), which is why the app does one picture per frame.

## Adding it to your firmware build

1. `./fetch_libs.sh` (puts the three libraries in `libs/`, pinned to the
   versions tested).
2. Copy or symlink this folder to `drivers/imgtool` in
   [badge-2024-software](https://github.com/emfcamp/badge-2024-software) (or your
   fork) and add one line to `drivers/micropython.cmake`:

   ```cmake
   include(${CMAKE_CURRENT_LIST_DIR}/imgtool/micropython.cmake)
   ```
3. Build the firmware as you normally do. Check with `import imgtool` on the badge.

**This has not been built for the badge yet.** It builds and passes its tests
as a MicroPython unix-port module on a PC; the ESP-IDF `micropython.cmake` is
untested because I have no ESP-IDF toolchain here. If it does not build, the
error will most likely be in that file: please send me the output.

## Testing on a PC

```sh
./fetch_libs.sh
cd test && make                       # builds the host driver, imgcli
python3 compare.py                    # output vs Pillow: formats, sizes, EXIF 1-8, bad files
python3 app_test.py                   # the gallery app using it, end to end
./asan.sh                             # AddressSanitizer + UBSan + leak check
# the real MicroPython module (unix port):
cd /path/to/micropython/ports/unix
make FROZEN_MANIFEST= USER_C_MODULES=/path/to/Tildagon-gallery/firmware \
     MICROPY_PY_BTREE=0 MICROPY_PY_FFI=0 MICROPY_PY_SSL=0
/path/to/Tildagon-gallery/firmware/imgtool/test/run_mp.sh ./build-standard/micropython
```

## Known limits

* JPEG and PNG only. GIF and BMP are not handled (the gallery's PC tool does
  those, and `ctx.image` still draws GIFs directly).
* Interlaced and 16-bit PNGs, arithmetic-coded and lossless JPEGs: reported as
  `NotImplementedError`.
* JPEGDEC fails on some unusual but valid files. I found one synthetic 1600 x
  1200 gradient that it cannot decode even from RAM; it is reported as
  `ValueError` and the app falls back. Real camera photos decoded fine in my
  tests, but I only had synthetic pictures to try.
* Thumbnails and shrunk copies go through RGB565 in the middle, so colours are
  accurate to about 4 levels out of 255 compared with Pillow.
* Timings on the badge are unmeasured. On a PC a 12 MP JPEG -> 480 px takes
  about 13 ms; the badge will be far slower (my guess: a few tenths of a second
  to a couple of seconds, and more for PNGs), but I have not run it there.
* The libraries' ESP32-S3 SIMD assembly is not enabled (it needs the Arduino
  build flags); turning it on is a possible later speed-up.
