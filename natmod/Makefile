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
# the bundled code uses 32-bit division helpers on some cores
LINK_RUNTIME = 1

include $(MPY_DIR)/py/dynruntime.mk

# make install: put the result where the app loads it from (the app's own folder)
install: $(MOD).mpy
	cp $(MOD).mpy ..
