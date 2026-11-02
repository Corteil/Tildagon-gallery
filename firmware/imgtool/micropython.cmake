# imgtool for CMake-based MicroPython ports (the badge's ESP-IDF build).
#
# In badge-2024-software, copy or symlink this folder to drivers/imgtool and
# add   include(${CMAKE_CURRENT_LIST_DIR}/imgtool/micropython.cmake)   to
# drivers/micropython.cmake. See README.md.
#
# The bitbank2 libraries are not in this repo: run fetch_libs.sh first (it
# puts them in libs/), or set IMGTOOL_LIBS to a folder that holds
# jpegdec/ jpegenc/ pngdec/.

set(IMGTOOL_DIR ${CMAKE_CURRENT_LIST_DIR})
if(NOT DEFINED IMGTOOL_LIBS)
    set(IMGTOOL_LIBS ${IMGTOOL_DIR}/libs)
endif()

set(IMGTOOL_J ${IMGTOOL_LIBS}/jpegdec/src)
set(IMGTOOL_E ${IMGTOOL_LIBS}/jpegenc/src)
set(IMGTOOL_P ${IMGTOOL_LIBS}/pngdec/src)

if(NOT EXISTS ${IMGTOOL_J}/JPEGDEC.cpp OR NOT EXISTS ${IMGTOOL_E}/JPEGENC.cpp OR NOT EXISTS ${IMGTOOL_P}/PNGdec.cpp)
    message(FATAL_ERROR "imgtool: libraries not found in ${IMGTOOL_LIBS}. Run firmware/imgtool/fetch_libs.sh")
endif()

set(IMGTOOL_ZLIB
    ${IMGTOOL_P}/adler32.c ${IMGTOOL_P}/crc32.c ${IMGTOOL_P}/infback.c ${IMGTOOL_P}/inffast.c
    ${IMGTOOL_P}/inflate.c ${IMGTOOL_P}/inftrees.c ${IMGTOOL_P}/zutil.c)
set(IMGTOOL_LIBSRC
    ${IMGTOOL_J}/JPEGDEC.cpp ${IMGTOOL_E}/JPEGENC.cpp ${IMGTOOL_P}/PNGdec.cpp ${IMGTOOL_ZLIB})

add_library(usermod_imgtool INTERFACE)

target_sources(usermod_imgtool INTERFACE
    ${IMGTOOL_DIR}/imgtool.c
    ${IMGTOOL_DIR}/imgcore.cpp
    ${IMGTOOL_LIBSRC}
)

target_include_directories(usermod_imgtool INTERFACE
    ${IMGTOOL_DIR} ${IMGTOOL_J} ${IMGTOOL_E} ${IMGTOOL_P}
)

# These definitions and the silenced warnings are for our files and the bitbank2
# ones only, not for the rest of the firmware.
#   __LINUX__                makes the libraries use <stdio.h> instead of Arduino.h
#   PNG_MAX_BUFFERED_PIXELS  room for PNG rows up to ~4000 pixels wide
set_source_files_properties(
    ${IMGTOOL_DIR}/imgcore.cpp ${IMGTOOL_LIBSRC}
    PROPERTIES
        COMPILE_DEFINITIONS "__LINUX__;PNG_MAX_BUFFERED_PIXELS=16386"
        COMPILE_OPTIONS "-w"
)

target_link_libraries(usermod INTERFACE usermod_imgtool)
