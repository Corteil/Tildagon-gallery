/* Stands in for Arduino.h. The bitbank2 headers fall back to it when none of
 * their platform macros is set; this gives them just what they use, and keeps
 * their file-reading (fopen) code out of the build. */
#ifndef SHIM_ARDUINO_H
#define SHIM_ARDUINO_H
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define PROGMEM
#define memcpy_P memcpy
#endif
