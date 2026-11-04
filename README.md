# Tildagon-gallery

A picture gallery for the EMF Camp badge (2024 Tildagon and the 2026 badge).
Pictures come from the SD card; browse them as a mosaic of thumbnails, open one
full screen, and step through with the badge buttons, the touch ring (2026), or
a USB keyboard.

**Status: early, but it runs on a real badge.** Tried on a 2024 Tildagon: the home carousel,
the viewer, thumbnails and resizing, the honeycomb, the Settings screen, the slideshow, the
flash copies, and the HDMI second screen (with the HDMI hexpansion; the slideshow can show a
brief burst of static on the TV when it starts). Not tried on a badge yet: the 4x4 grid and
focus ring, search, the 480 and 720 px copy sizes, and the 2026 badge's touch ring and joystick.
Please try it and tell me what breaks.

## Using it

Put pictures in a `Pictures` folder on the SD card (`/sdcard/Pictures`, or
`/sdcard_1/Pictures` for the Dual uSD hexpansion). JPEG, PNG and GIF (first frame) are
listed; the badge's picture loader can't draw BMP, so `tools/prepare.py` converts those. Folders inside it are albums: CONFIRM opens one, CANCEL goes back up.

The app opens on a carousel of four tiles, like the badge's other apps: LEFT/RIGHT
move between them (they wrap round), CONFIRM opens one, CANCEL goes back to the
carousel, and CANCEL on the carousel sends the app to the background.

* **Pictures**: the mosaic of cells (pictures, and albums first). CANCEL clears a search,
  then goes up out of an album, then back to the carousel.
* **Slideshow**: starts the slideshow from the first picture.
* **Search**: type part of a file name (USB keyboard, or on the badge: UP/DOWN
  picks a letter, RIGHT adds it, LEFT deletes, CONFIRM searches and shows the matches).
* **Settings** (LEFT/RIGHT change, UP/DOWN pick a row, all remembered):
  **Source** (CONFIRM: choose which card to browse, every `/sdcard*` that is there, or the
  **Flash** copy, below),
  mosaic layout (3x3 grid, 4x4 grid, honeycomb, focus ring). The focus ring keeps
  the selected picture in the middle. In the honeycomb the pictures keep their cells and
  the arrows move the highlight; CONFIRM swaps the highlighted picture with the middle
  cell (CONFIRM on the middle one opens it). With more than 19 pictures, moving off
  the edge scrolls the outer 18 cells a page; the middle one only changes when you swap, slide timer, slide order (in order or
  shuffled), loop the slideshow or stop at the end, captions (file name and
  size under the picture), **HDMI screen** (see below), the size of copies kept in flash (240, 480 or 720 px),
  sort order (name, newest or oldest first), and "Clear kept" (CONFIRM) which
  empties the flash copies. Keeping refuses when less than 300 KB of flash would
  be left.

**HDMI second screen.** With the HDMI hexpansion fitted and a badge firmware that
has `display.Screen` (hazanjon's `feature/hdmi-mirror`), switch Settings > HDMI screen
on. The picture you open in the viewer or slideshow then goes to the TV at 240 x 240
(the same frame is sent again every 350 ms, because the hexpansion shows static after half a second of silence), and the badge's own screen shows the
file name, position and slideshow timer. Leaving the viewer or slideshow, leaving the app, or switching it off, hands
the port back to the normal mirror. Switching the option on starts the badge
mirroring to the HDMI hexpansion by itself (it finds it by its EEPROM id), so the HDMI Manager
app isn't needed. Without HDMI fitted you get a "No HDMI hexpansion found" toast and nothing else changes. 480 x 480 stills need a new frame type on
the RP2350 side (see the plan in the hexpansion repo).

| | Browse | Viewer | Slideshow |
|---|---|---|---|
| Move | UP / DOWN / LEFT / RIGHT | RIGHT or DOWN next, LEFT or UP previous | LEFT / RIGHT skip |
| CONFIRM | open a picture or album | keep in flash / take out of flash | pause / play |
| UP / DOWN | | | timer 2 to 60 s (remembered) |
| Back / quit | CANCEL (F) back up, then to the carousel | CANCEL back to the mosaic | CANCEL stops |
| Touch ring (2026) | slide a finger round it to move through the pictures | same | same |
| USB keyboard | arrows, Enter, Esc, Space / Backspace for next / previous, a letter jumps to the next name starting with it | same | |

Holding a direction repeats it.

### Keeping pictures in flash

The HDMI hexpansion and an SD hexpansion can't both be fitted, so to use the
gallery with HDMI the pictures have to be in the badge itself. In the viewer,
CONFIRM keeps a resized copy (240 px, or 480 or 720 from Settings: the bigger ones are for the HDMI display, the badge's own screen only shows 240) in the badge's flash, in
`/gallery/kept`; CONFIRM again takes it out. At most **10** are kept: keeping an
11th drops the oldest. Pick **Flash (kept)** under Settings > Source to browse them (it opens
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
| `hdmi.py` | the HDMI hexpansion as an independent second screen (`display.Screen`, 240 x 240 `TDHD` for now) |
| `tools/prepare.py` | the PC tool |
| `tests/` | PC tests (`tests/run_all.sh`); a GitHub Actions job runs them on every push |
| `tools/badge.py`, `tools/selftest.py` | deploy to a badge and run the on-badge self-test |
| `imgtool.py`, `_imgtool.mpy` | on-badge resizing (Python + prebuilt native code); source and tests in `natmod/` |

## Credits

`_imgtool.mpy` is built on [JPEGDEC](https://github.com/bitbank2/JPEGDEC),
[PNGdec](https://github.com/bitbank2/PNGdec) and [JPEGENC](https://github.com/bitbank2/JPEGENC)
by Larry Bank (bitbank2), Apache License 2.0; see `NOTICE`. The app itself is MIT (`LICENSE`).

## Planned

480 x 480 stills on the HDMI display (needs a new frame type in the hexpansion's firmware), and
trying the remaining features on real badges: the 4x4 grid, focus ring, search, the larger copy
sizes and the 2026 badge's extra inputs.
