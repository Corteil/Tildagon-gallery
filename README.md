# Tildagon-gallery

A picture gallery for the EMF Camp badge (2024 Tildagon and the 2026 badge).
Pictures come from the SD card; browse them as a mosaic of thumbnails, open one
full screen, and step through with the badge buttons, the touch ring (2026), or
a USB keyboard.

**Status: early. Everything here is tested with stand-ins and on a PC; none of
it has been run on a real badge yet.** Please try it and tell me what breaks.

## Using it

Put pictures in a `Pictures` folder on the SD card (`/sdcard/Pictures`, or
`/sdcard_1/Pictures` for the Dual uSD hexpansion). JPEG, PNG, BMP and GIF are
listed. The first four tiles of the mosaic are not pictures:

* **Search**: type part of a file name (USB keyboard, or on the badge: UP/DOWN
  picks a letter, RIGHT adds it, LEFT deletes, CONFIRM searches). CANCEL in the
  mosaic clears the search.
* **Storage**: choose which card to browse (every `/sdcard*` that is there) or
  the **Flash** copy (below). The choice is remembered.
* **Slides**: start the slideshow.
* **Settings**: LEFT/RIGHT change the mosaic layout (3x3 grid, 4x4 grid,
  honeycomb, focus ring; the last two keep the selected picture in the middle) and the slide timer; CONFIRM on "Clear kept" empties
  the flash copies. Both are remembered.

| | Browse | Viewer | Slideshow |
|---|---|---|---|
| Move | UP / DOWN / LEFT / RIGHT | RIGHT or DOWN next, LEFT or UP previous | LEFT / RIGHT skip |
| CONFIRM | open / use a tile | keep in flash / take out of flash | pause / play |
| UP / DOWN | | | timer 2 to 60 s (remembered) |
| Back / quit | CANCEL (F) | CANCEL back to the mosaic | CANCEL stops |
| Touch ring (2026) | slide a finger round it to move through the pictures | same | same |
| USB keyboard | arrows, Enter, Esc, Space / Backspace for next / previous, a letter jumps to the next name starting with it | same | |

Holding a direction repeats it.

### Keeping pictures in flash

The HDMI hexpansion and an SD hexpansion can't both be fitted, so to use the
gallery with HDMI the pictures have to be in the badge itself. In the viewer,
CONFIRM keeps a resized copy (at most 240 px) in the badge's flash, in
`/gallery/kept`; CONFIRM again takes it out. At most **10** are kept: keeping an
11th drops the oldest. Pick **Flash (kept)** in Storage to browse them (it opens
by itself when there is no card).

### Slideshow

Each picture is resized if need be, and the next few are copied into a RAM disk
in PSRAM so the card isn't read between slides. It moves on when the timer is
up and the next picture is ready. If the firmware can't mount the RAM disk, or
drawing from it fails, it quietly reads from the card instead (`ctx.image()`
only takes file paths, so this is the part most in need of testing on a badge).

## Thumbnails and big pictures

The badge cannot draw very large pictures, so there are two ways to get small
ones, which can be combined:

* **On the badge**, with `imgtool.py` and `_imgtool.mpy` (source in [natmod](natmod)),
  which live in the app's own folder: no firmware change, nothing installed
  elsewhere. Thumbnails are made as you browse, and a
  picture over `MAX_PIXELS` is shrunk into a `.view240` copy when you open it.
* **On a PC**, no firmware changes: `python tools/prepare.py ~/Photos /path/to/sdcard/Pictures`
  (needs Pillow) shrinks the pictures, turns them the right way up and writes
  the thumbnails to `.thumbs/`. It also handles GIF/BMP/WebP/TIFF.
  `prepare.py --test-ladder DIR` writes test pictures of growing size to find
  your badge's real limit for `MAX_PIXELS`.

Without either, pictures still show if they are under `MAX_PIXELS`, and the
mosaic shows coloured tiles with the first letter of the name.

## Testing on a Raspberry Pi and the badges

On the Pi (or any Debian/Ubuntu PC):

```sh
git clone https://github.com/Corteil/Tildagon-gallery && cd Tildagon-gallery
git checkout initial-gallery-app
natmod/test/pi_setup.sh     # installs mpremote + Pillow, builds the C core, runs the PC tests
```

Then plug a badge in over USB (log out and in once if the script added you to
`dialout`) and:

```sh
python3 tools/badge.py test                  # copy the app to /apps/gallery and run the self-test
python3 tools/badge.py test --photo /sdcard/Pictures/some.jpg   # also time a real picture
python3 tools/badge.py info                  # MicroPython version, mpy number, free memory
python3 tools/badge.py ports                 # list badges when more than one is plugged in
python3 tools/badge.py test --port /dev/ttyACM1
```

The self-test (`tools/selftest.py`) makes its own pictures, checks thumbnails,
resizing, error handling and memory use, and prints `SELFTEST PASSED` or
`FAILED` with timings. Run it on each badge; the 2024 and 2026 badges may need
different `_imgtool.mpy` builds if their MicroPython differs (`info` shows
the `mpy` number: the prebuilt file is for 11014). Please send me the output.

## Layout of the repo

| | |
|---|---|
| `app.py`, `__init__.py`, `metadata.json`, `tildagon.toml` | the app |
| `inputs.py`, `touch_scroll.py` | buttons, touch ring and keyboard |
| `layouts.py` | mosaic layouts: 3x3 and 4x4 grids, honeycomb, focus ring |
| `scanner.py`, `imginfo.py`, `thumbs.py` | finding pictures, reading sizes from headers, making thumbnails |
| `storage.py`, `keep.py`, `stage.py` | which card, the 10 pictures kept in flash, the slideshow's PSRAM RAM disk |
| `tools/prepare.py` | the PC tool |
| `tests/` | PC tests (`tests/run_all.sh`); a GitHub Actions job runs them on every push |
| `tools/badge.py`, `tools/selftest.py` | deploy to a badge and run the on-badge self-test |
| `imgtool.py`, `_imgtool.mpy` | on-badge resizing (Python + prebuilt native code); source and tests in `natmod/` |

## Planned

A second display on the HDMI hexpansion (mirroring first), and trying all of this on real badges: the layouts, search, storage picker, flash copies and the slideshow have only been run against stand-ins so far.
