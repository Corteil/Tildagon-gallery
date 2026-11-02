#!/usr/bin/env python3
"""Wrapper around MicroPython's tools/mpy_ld.py for building _imgtool.mpy.

    mpy_ld_wrap.py MPY_LD.PY [mpy_ld arguments ...]

Two problems with linking several object files for the ESP32-S3 (xtensawin):

1. mpy_ld names its table of pointers after the section a pointer refers to
   (".rodata.str1.1+0x10"), so two object files that both have such a section
   share one entry and one of them reads the wrong data (string literals and
   lookup tables turn into garbage). We give every section of every object file
   a name of its own first.
2. Espressif's xtensa-esp-elf-gcc defaults to a big-endian core. The libgcc and
   libm that the build finds are the big-endian ones; use the esp32s3 ones.
3. Read-only data is aligned only as far as its type needs, but the bitbank2 code
   reads byte tables through int pointers (JPEGENC's hufftable). Unaligned 32-bit
   reads work on x86 and silently read the wrong word on the ESP32, so give all
   read-only data 4-byte alignment.

4. For a pointer to a global symbol plus an offset (the encoder's
   &ulMagnitudeFix[1024]) mpy_ld puts the offset in the name of its table entry but
   forgets to add it to the address, so the pointer points at the symbol itself.
   We run a patched copy of mpy_ld.py that adds it. (A copy in the build folder;
   the MicroPython tree is not touched.)

Anything that is not the link step (--preprocess) is passed straight through.
"""
import os
import re
import subprocess
import sys

OBJCOPY = os.environ.get("OBJCOPY", "xtensa-esp32-elf-objcopy")
OBJDUMP = os.environ.get("OBJDUMP", "xtensa-esp32-elf-objdump")
MULTILIB = os.environ.get("XTENSA_MULTILIB", "esp32s3")
RENAME = re.compile(r"^\.(text|rodata|data\.rel\.ro|data|bss)(\.|$)")


def sections(path):
    out = subprocess.run([OBJDUMP, "-h", path], capture_output=True, text=True, check=True).stdout
    return [m.group(1) for m in re.finditer(r"^\s*\d+\s+(\S+)\s+[0-9a-f]+", out, re.M)]


def uniquify(path, n, outdir):
    dest = os.path.join(outdir, "%d_%s" % (n, os.path.basename(path)))
    args = [OBJCOPY]
    for s in sections(path):
        if RENAME.match(s):
            args += ["--rename-section", "%s=%s.u%d" % (s, s, n)]
            if s.startswith((".rodata", ".data.rel.ro")):
                args += ["--set-section-alignment", "%s.u%d=4" % (s, n)]
    subprocess.run(args + [path, dest], check=True)
    return dest


def multilib(path):
    """The esp32s3 copy of a libgcc.a / libm.a, if there is one."""
    d, f = os.path.split(path)
    alt = os.path.join(d, MULTILIB, f)
    return alt if os.path.exists(alt) else path


BUGGY = "env.got_entries[name] = GOTEntry(name, s, existing)"
FIXED = 'env.got_entries[name] = GOTEntry(name, s, existing if s_type == "STT_SECTION" else r["r_addend"])'


def patched_mpy_ld(mpy_ld, outdir):
    src = open(mpy_ld).read()
    if BUGGY not in src:
        return mpy_ld  # a newer mpy_ld that has been fixed
    dest = os.path.join(outdir, "mpy_ld_patched.py")
    with open(dest, "w") as f:
        f.write(src.replace(BUGGY, FIXED))
    tools = os.path.dirname(os.path.abspath(mpy_ld))
    os.environ["PYTHONPATH"] = os.pathsep.join([tools, os.path.join(tools, "..", "py"), os.environ.get("PYTHONPATH", "")])
    return dest


def main():
    mpy_ld, args = sys.argv[1], sys.argv[2:]
    if "--qstrs" in args:
        out = []
        outdir = os.path.join(os.path.dirname(os.path.abspath(args[args.index("-o") + 1])), "uniq")
        os.makedirs(outdir, exist_ok=True)
        n = 0
        for a in args:
            if a.endswith(".o"):
                n += 1
                a = uniquify(a, n, outdir)
            elif a.startswith("-l") and a.endswith((".a",)):
                a = "-l" + multilib(a[2:])
            out.append(a)
        args = out
    if "--qstrs" in args:
        mpy_ld = patched_mpy_ld(mpy_ld, os.path.dirname(os.path.abspath(args[args.index("-o") + 1])))
    sys.exit(subprocess.call([sys.executable, mpy_ld] + args))


main()
