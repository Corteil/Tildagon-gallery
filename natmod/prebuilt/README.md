`_imgtool.mpy` here is built for the badge (xtensawin / ESP32-S3) against
MicroPython 1.28.0 (commit e0e9fbb, the version pinned by badge-2024-software at
the time), mpy format 6.3.

A native module is tied to the exact MicroPython it was built against. Check
your badge first: in the REPL, `import sys; print(sys.implementation._mpy)`
must print `11014`, and `sys.implementation.version` should be `(1, 28, 0, '')`.
If either differs, build your own: see ../README.md.
