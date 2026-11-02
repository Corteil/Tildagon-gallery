#include "JPEGDEC.h"
#include "jpeg.inl"

/* JPEGInit is private to the library in C builds; expose it to core.c */
int img_jpeg_init(JPEGIMAGE *p) { return JPEGInit(p); }
int img_jpeg_decode(JPEGIMAGE *p, int opts) { p->iXOffset = 0; p->iYOffset = 0; p->iOptions = opts; return DecodeJPEG(p); }
