# Host build of the core, for tests. LIBS: folder holding jpegdec/ jpegenc/ pngdec/ (see ../fetch_libs.sh)
LIBS ?= $(abspath ../libs)
J = $(LIBS)/jpegdec/src
E = $(LIBS)/jpegenc/src
P = $(LIBS)/pngdec/src
CFLAGS = -O2 -w -DNO_SIMD -DPNG_MAX_BUFFERED_PIXELS=16386 -I../shim -I$(J) -I$(E) -I$(P) -I..
# JPEGDEC.h defines HAS_NEON on aarch64 even with NO_SIMD, without including the header
ifneq (,$(filter aarch64 arm64,$(shell uname -m)))
CFLAGS += -include arm_neon.h
endif
Z = adler32 crc32 infback inffast inflate inftrees zutil
SRCS = imgcli.c hostalloc.c ../core.c ../lib_jpegdec.c ../lib_jpegenc.c ../lib_pngdec.c $(Z:%=$(P)/%.c)
imgcli: $(SRCS) ../imgcore.h
	$(CC) $(CFLAGS) -o $@ $(SRCS)
clean:
	rm -f imgcli
