# Handoff: Tildagon gallery, for a Claude Code session on the Raspberry Pi

You are picking this up on the Pi that has the badge(s) plugged in over USB.
Everything below was built and tested on stand-ins in a cloud container. **Nothing
in "Not yet verified on hardware" has run on a real badge.** Your job is to find
out what works and fix what doesn't.

Owner: Brian (GitHub `Corteil`), prefers Python / MicroPython / CircuitPython.
Repo: https://github.com/Corteil/Tildagon-gallery, branch `initial-gallery-app`.
HDMI hexpansion repo: https://github.com/Corteil/rp2350-hdmi-hexpansion
(plan PR #2, branch `docs/stills-second-screen-plan`, file `hdmi-stills-mode-plan.md`).

## What the app is

A picture gallery for the EMF Camp Tildagon badge (2024 Tildagon and 2026
Spaceagon). Browse tile layouts (3x3, 4x4, honeycomb, focus ring), viewer,
slideshow, picture search, storage picker, settings, albums (sub-folders), up to
10 resized copies kept in the badge's flash (for use without an SD card), and
an HDMI second screen.

Key files: `app.py` (everything stateful), `layouts.py`, `hdmi.py`, `keep.py`,
`stage.py` (slideshow RAM disk in PSRAM), `thumbs.py`, `imginfo.py`, `scanner.py`,
`storage.py` (settings in `/gallery/settings.txt`), `imgtool.py` + `_imgtool.mpy`
(native resize/thumbnail module, xtensawin, MicroPython 1.28.0 / mpy 11014).
The app opens on a home carousel of four tiles (`HOME` in `app.py`: Pictures, Slideshow, Search, Settings; state `home`). Cells in the picture mosaic are pictures, or albums which start with `@dir:<path>`. The storage picker is under Settings > Source.

## First thing to do

```
pip install mpremote            # if not there already
git clone https://github.com/Corteil/Tildagon-gallery && cd Tildagon-gallery
git checkout initial-gallery-app
bash tests/run_all.sh           # PC tests; must end ALL ... PASSED  (natmod/test/pi_setup.sh installs deps)
python3 tools/badge.py ports    # list badges
python3 tools/badge.py info     # MicroPython version, mpy number, free memory
python3 tools/badge.py test     # deploy to /apps/gallery and run the on-badge self-test
```

`badge.py test --photo /sdcard/Pictures/x.jpg` also times a real picture (mounts
the SD hexpansion itself if the SD Card app hasn't). `--port /dev/ttyACM1` picks
a badge when several are connected. If `info` shows an mpy version other than
11014, `_imgtool.mpy` won't load: rebuild it (see `natmod/Makefile`, README) or
the app falls back to no thumbnails/resizing (it should still run).

## Not yet verified on hardware

1. The on-badge self-test (`tools/selftest.py`), i.e. imgtool loads, thumbnails,
   resize, memory use.
2. `ctx.image()` drawing from the RAM disk (`stage.py`) during the slideshow.
3. Hex / circular clipping (honeycomb, focus ring) renders correctly.
4. Flash keep (CONFIRM in viewer): copies land in `/gallery/kept`, max 10,
   refuses with under 300 KB flash free, "Clear kept" works.
5. Slideshow: timer, shuffle, loop, captions, prepare-ahead (`STAGE_AHEAD=3`).
6. **HDMI second screen** (newest). Needs the badge fork firmware
   `hazanjon/badge-2024-software` branch `feature/hdmi-mirror` (has
   `display.attach_mirror / detach_mirror / is_mirror_active / Screen`) and the
   HDMI hexpansion mirroring. In the app: Settings > HDMI screen > On, open a
   picture, then run a slideshow. Expect: TV shows the picture at 240x240, the
   badge screen shows file name, n/N, timer ring; leaving the app (or switching
   it off) restores the mirror. With no HDMI: toast "No HDMI mirror found".
   `hdmi.py` prints `gallery: second screen failed:` / `HDMI draw failed` /
   `mirror re-attach failed` on errors; capture the REPL output
   (`python3 tools/badge.py repl`).

Note: an HDMI hexpansion and an SD hexpansion can't be fitted together, hence
the flash keep. HDMI testing therefore uses kept copies (keep a few pictures
first with an SD hexpansion, then swap hexpansions).

## How to work

- Fix things in the repo, run `bash tests/run_all.sh` (it covers app logic with
  stubbed badge modules, MODE 2024/2026 x KB 0/1), then redeploy with
  `python3 tools/badge.py test`. CI (`.github/workflows/test.yml`) runs the same.
- If a bug only shows on hardware, add a test to `tests/test_gallery.py` that
  reproduces it with the stubs if you can.
- Commit small, push to `initial-gallery-app`, and report findings to Brian
  (what passed, what failed, REPL output).
- Keep new files in `FILES` in `tools/badge.py` or they won't be deployed.
- Constraints worth knowing: `ctx.image(path, x, y, w, h)` takes only a file
  path, loads the whole file and decodes PNG/GIF/JPEG (no BMP) to RGBA, so large
  pictures run out of memory; hence the 240 px (`MAX_PIXELS`) limit on the badge
  screen and the shrunk `.view<size>` copies.

## Next steps after hardware results

1. Fix whatever failed above.
2. 480x480 HDMI stills: add a kept-size/HDMI option that uses `.view480` copies
   and a `TDHS` driver via `display.Screen(width=480, height=480, ...)`, with a
   fallback to 240 over `TDHD` when unsupported. Needs RP2350 support first
   (plan in the hexpansion repo; `TDHS` = "stills", 480x480 RGB565 byte-swapped,
   flags byte after the header, bit 0 = round mask).
3. RP2350 firmware: implement `TDHS` in `firmware/pio-testcard/src/main.c`
   (hexpansion repo), bench per the plan.
4. Merge PR #2 in the hexpansion repo; open a PR for `initial-gallery-app`.

## Hints

- `hdmi.py` is a small working wrapper around `display.Screen`; hazanjon's
  https://github.com/hazanjon/display_manager is the reference app for it.
- Layout interface: `shape` ("rect"/"hex"/"circle"), `tiles(sel, n)` ->
  [(index, x, y, w, h)], `move(sel, d, n)`, `focus`.
- Settings keys: folder, seconds, layout, shuffle, loop, captions, hdmi, keep_px, sort.
