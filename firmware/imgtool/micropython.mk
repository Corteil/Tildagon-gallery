# MicroPython "make" ports (unix, used for testing on a PC):
#   make -C ports/unix USER_C_MODULES=/path/to/firmware IMGTOOL_LIBS=/path/to/bitbank2
IMGTOOL_DIR := $(USERMOD_DIR)
IMGTOOL_LIBS ?= $(IMGTOOL_DIR)/libs
J := $(IMGTOOL_LIBS)/jpegdec/src
E := $(IMGTOOL_LIBS)/jpegenc/src
P := $(IMGTOOL_LIBS)/pngdec/src

SRC_USERMOD += $(IMGTOOL_DIR)/imgtool.c
SRC_USERMOD_CXX += $(IMGTOOL_DIR)/imgcore.cpp $(J)/JPEGDEC.cpp $(E)/JPEGENC.cpp $(P)/PNGdec.cpp
IMGTOOL_ZSRC := $(addprefix $(P)/,adler32.c crc32.c infback.c inffast.c inflate.c inftrees.c zutil.c)
SRC_USERMOD += $(IMGTOOL_ZSRC)
# the bundled zlib has fall-through cases and the like: not ours to fix
$(addprefix $(BUILD)/,$(IMGTOOL_ZSRC:.c=.o)): CFLAGS += -w

CFLAGS_USERMOD += -I$(IMGTOOL_DIR) -I$(P) -D__LINUX__
CXXFLAGS_USERMOD += -w -I$(IMGTOOL_DIR) -I$(J) -I$(E) -I$(P) -std=c++11 -D__LINUX__ -DPNG_MAX_BUFFERED_PIXELS=16386
LIBS_USERMOD += -lstdc++
