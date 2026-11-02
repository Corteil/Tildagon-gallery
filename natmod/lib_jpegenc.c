#include "JPEGENC.h"
#include "jpegenc.inl"

int img_jpeg_add_frame(JPEGE_IMAGE *p, JPEGENCODE *e, uint8_t *px, int pitch) { return JPEGAddFrame(p, e, px, pitch); }
