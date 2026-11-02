# Tildagon-gallery

A picture gallery for the EMF Camp badge (2024 Tildagon and the 2026 badge).
Pictures come from the SD card; browse them as a mosaic of thumbnails, open one
full screen, and step through with the badge buttons, the touch ring (2026), or
a USB keyboard.

**Status: early. Everything here is tested with stand-ins and on a PC; none of
it has been run on a real badge yet.** Please try it and tell me what breaks.

## Using it

Put pictures in `/sdcard/Pictures` (change `ROOT` in `app.py`). JPEG, PNG, BMP
and GIF are listed.

| | Browse | Viewer |
|---|---|---|
| Move | UP / DOWN / LEFT / RIGHT | RIGHT or DOWN next, LEFT or UP previous |
| Open | CONFIRM | |
| Back / quit | CANCEL (F) | CANCEL back to the mosaic |
| Touch ring (2026) | slide a finger round it to move through the pictures | same |
| USB keyboard | arrows, Enter, Esc, Space / Backspace for next / previous, a letter jumps to the next name starting with it | same |

Holding a direction repeats it.

## Thumbnails and big pictures

The badge cannot draw very large pictures, so there are two ways to get small
ones, which can be combined:

* **On the badge**, with `imgtool.py` and `_imgtool.mpy` (source in [natmod](natmod)),
  which live in the app's own folder: no firmware change, nothing installed
  elsewhere. Thumbnails are made as you browse, and a
  picture over `MAX_PIXELS` is shrunk into a `.view` copy when you open it.
* **On a PC**, no firmware changes: `python tools/prepare.py ~/Photos /path/to/sdcard/Pictures`
  (needs Pillow) shrinks the pictures, turns them the right way up and writes
  the thumbnails to `.thumbs/`. It also handles GIF/BMP/WebP/TIFF.
  `prepare.py --test-ladder DIR` writes test pictures of growing size to find
  your badge's real limit for `MAX_PIXELS`.

Without either, pictures still show if they are under `MAX_PIXELS`, and the
mosaic shows coloured tiles with the first letter of the name.

## Layout of the repo

| | |
|---|---|
| `app.py`, `__init__.py`, `metadata.json`, `tildagon.toml` | the app |
| `inputs.py`, `touch_scroll.py` | buttons, touch ring and keyboard |
| `layouts.py` | mosaic layouts (3x3 and 4x4 grids so far) |
| `scanner.py`, `imginfo.py`, `thumbs.py` | finding pictures, reading sizes from headers, making thumbnails |
| `tools/prepare.py` | the PC tool |
| `imgtool.py`, `_imgtool.mpy` | on-badge resizing (Python + prebuilt native code); source and tests in `natmod/` |

## Planned

Slideshow with an adjustable timer, the honeycomb and focus-ring mosaic layouts,
a settings screen, and a second display on the HDMI hexpansion.
