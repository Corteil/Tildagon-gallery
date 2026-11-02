#include "PNGdec.h"
#include "png.inl"

/* these are private to the library in C builds; expose them to core.c */
int img_png_init(PNGIMAGE *p) { return PNGInit(p); }
int img_png_decode(PNGIMAGE *p, void *user, int opts) { return DecodePNG(p, user, opts); }
void img_png_rgb565(PNGDRAW *d, uint16_t *px, int endian, uint32_t bkgd, int alpha) { PNGRGB565(d, px, endian, bkgd, alpha); }
