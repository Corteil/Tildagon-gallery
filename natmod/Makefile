# Builds _imgtool.mpy, a native module you copy to the badge's /lib.
#
#   make ARCH=xtensawin MPY_DIR=/path/to/micropython     for the badge (ESP32-S3)
#   make ARCH=x64       MPY_DIR=/path/to/micropython     for the PC unix port (tests)
#
# Needs the bitbank2 libraries: run ./fetch_libs.sh first.
MPY_DIR ?= ../../micropython/micropython
MOD = _imgtool
ARCH ?= xtensawin
LIBS ?= $(abspath libs)
J = $(LIBS)/jpegdec/src
E = $(LIBS)/jpegenc/src
P = $(LIBS)/pngdec/src

SRC = imgtool_mod.c core.c shim.c lib_jpegdec.c lib_jpegenc.c lib_pngdec.c \
      $(addprefix $(P)/,adler32.c crc32.c infback.c inffast.c inflate.c inftrees.c)

CFLAGS += -fno-tree-loop-distribute-patterns -DNO_SIMD -DPNG_MAX_BUFFERED_PIXELS=16386 -I. -Ishim -I$(J) -I$(E) -I$(P) -Os -w
# Without per-symbol sections mpy_ld mixes up the .rodata of different object files
# (tables read as garbage on the badge), so give every symbol its own section.
CFLAGS += -fdata-sections
# Espressif's current xtensa-esp-elf-gcc defaults to a generic BIG-endian core; the badge's
# ESP32-S3 is little-endian, so say which chip (also picks the matching libgcc/libm).
# Older xtensa-esp32-elf-gcc toolchains don't need or know this flag.
XTENSA_LIB := $(abspath $(dir $(realpath $(shell command -v xtensa-esp32-elf-gcc 2>/dev/null)))../lib)
ifneq (,$(wildcard $(XTENSA_LIB)/xtensa_esp32s3.so))
CFLAGS += -mdynconfig=$(XTENSA_LIB)/xtensa_esp32s3.so
endif
# the bundled code uses 32-bit division helpers on some cores
LINK_RUNTIME = 1

include $(MPY_DIR)/py/dynruntime.mk

# See mpy_ld_wrap.py: unique section names per object file, little-endian libgcc/libm
ifeq ($(ARCH),xtensawin)
MPY_LD = $(PYTHON) $(CURDIR)/mpy_ld_wrap.py $(MPY_DIR)/tools/mpy_ld.py
endif

# make install: put the result where the app loads it from (the app's own folder)
install: $(MOD).mpy
	cp $(MOD).mpy ..
