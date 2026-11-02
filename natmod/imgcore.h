/* imgcore: decode a JPEG or PNG, shrink it, encode the result.
 *
 * Plain C, built on JPEGDEC, PNGdec and JPEGENC by Larry Bank. It knows nothing
 * about MicroPython: file access comes in through the imgio struct and the
 * encoded file goes out as a buffer.
 */
#ifndef IMGCORE_H
#define IMGCORE_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    void *ctx;
    int size;                                  /* file length in bytes */
    int (*read)(void *ctx, uint8_t *buf, int len);  /* bytes read, <0 on error */
    int (*seek)(void *ctx, int pos);           /* 0 on success */
} imgio_t;

enum {                    /* return values; 0 is success */
    IMG_OK = 0,
    IMG_E_FORMAT = -1,    /* not a JPEG/PNG, or damaged */
    IMG_E_UNSUPPORTED = -2, /* interlaced or 16-bit PNG, lossless/arithmetic JPEG ... */
    IMG_E_MEMORY = -3,
    IMG_E_IO = -4,
    IMG_E_PARAM = -5
};

enum {
    IMG_THUMB_PNG = 0,    /* centre-cropped square, size x size, as PNG */
    IMG_FIT_JPEG = 1      /* whole picture, longest side <= size, as JPEG */
};

typedef struct {
    uint8_t *data;        /* encoded file; free with img_free() */
    size_t len;
    int width, height;    /* size of the picture that was encoded */
    int src_width, src_height; /* size of the picture that was read */
} imgout_t;

int img_make(const imgio_t *in, int mode, int size, int quality, imgout_t *out);
void img_free(void *p);

/* Reads only the header. width/height in the picture's own orientation
 * before any EXIF rotation. */
int img_info(const imgio_t *in, int *width, int *height);

/* Supplied by whoever links this in: where memory comes from. The MicroPython
 * module uses the MicroPython heap (which is PSRAM on the badge); the PC tests
 * use malloc. img_alloc may raise instead of returning NULL. */
void *img_alloc(size_t n);
void img_release(void *p);

#endif
