#!/usr/bin/env python3
"""Copy the gallery app to a badge and test it. Runs on any PC or Raspberry Pi
with the badge plugged in over USB. Needs:  pip install mpremote

  badge.py deploy          copy the app to /apps/<name> on the badge
  badge.py test            deploy, then run the on-badge self-test
  badge.py test --photo /sdcard/Pictures/x.jpg    also time a real picture
  badge.py info            MicroPython version, mpy number, free memory
  badge.py repl            open a REPL (Ctrl-] to leave)

A photo under /sdcard needs the SD hexpansion mounted. If the SD Card app on the
badge has not mounted it, the test mounts it itself (hexpansion slot --sd-port,
default 4, the same SPI setup as the SD hexpansion app).

Options: --name gallery (folder under /apps), --port /dev/ttyACM0 (default: first
badge found; list them with `badge.py ports`)."""
import argparse, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FILES = ["__init__.py", "app.py", "inputs.py", "layouts.py", "scanner.py", "imginfo.py",
         "thumbs.py", "touch_scroll.py", "imgtool.py", "_imgtool.mpy", "metadata.json", "tildagon.toml"]


# Mounts the SD hexpansion in slot SD_PORT at /sdcard unless it is already there.
SD_MOUNT = (
    "import os,vfs\n"
    "try:\n os.listdir('/sdcard')\n"
    "except OSError:\n"
    " from machine import SDCard\n"
    " from system.hexpansion.config import HexpansionConfig\n"
    " c=HexpansionConfig(%d)\n"
    " c.ls_pin[0].init(c.ls_pin[0].OUT);c.ls_pin[0].on()\n"
    " vfs.mount(SDCard(slot=3,sck=c.pin[2],cs=c.pin[0],mosi=c.pin[1],miso=c.pin[3]),'/sdcard')\n"
)


def mp(port, *args, check=True):
    cmd = ["mpremote"] + (["connect", port] if port else []) + list(args)
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def deploy(port, name):
    dest = ":/apps/" + name
    mp(port, "fs", "mkdir", dest, check=False)
    for f in FILES:
        mp(port, "fs", "cp", os.path.join(ROOT, f), dest + "/" + f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["deploy", "test", "info", "repl", "ports"])
    ap.add_argument("--name", default="gallery")
    ap.add_argument("--port")
    ap.add_argument("--photo")
    ap.add_argument("--sd-port", type=int, default=4, help="hexpansion slot of the SD card (default 4)")
    a = ap.parse_args()
    if a.cmd == "ports":
        mp(None, "connect", "list")
    elif a.cmd == "deploy":
        deploy(a.port, a.name)
    elif a.cmd == "info":
        mp(a.port, "exec", "import sys,gc;print(sys.implementation.version,sys.implementation._mpy,gc.mem_free())")
    elif a.cmd == "repl":
        mp(a.port, "repl")
    else:
        deploy(a.port, a.name)
        dest = ":/apps/%s/selftest.py" % a.name
        mp(a.port, "fs", "cp", os.path.join(HERE, "selftest.py"), dest)
        arg = repr(a.photo) if a.photo else "None"
        # system.scheduler must load first: importing the badge OS eventbus directly is circular
        mount = SD_MOUNT % a.sd_port if a.photo and a.photo.startswith("/sdcard") else ""
        code = (mount + "import sys;sys.path.insert(0,'/apps');import system.scheduler;"
                "m=__import__('%s.selftest',None,None,['run']);m.run(%s)" % (a.name, arg))
        r = subprocess.run(["mpremote"] + (["connect", a.port] if a.port else []) + ["exec", code],
                           capture_output=True, text=True)
        print(r.stdout, r.stderr)
        mp(a.port, "fs", "rm", dest, check=False)
        sys.exit(0 if "SELFTEST PASSED" in r.stdout else 1)


main()
