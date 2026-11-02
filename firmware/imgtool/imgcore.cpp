/* imgcore: see imgcore.h.
 *
 * Build defines (set by micropython.cmake / the test Makefile):
 *   __LINUX__                  makes the bitbank2 headers use <stdio.h> not Arduino.h
 *   PNG_MAX_BUFFERED_PIXELS    widest PNG row buffer (we ask for 16386 bytes)
 *   ESP_PLATFORM               use heap_caps_* so big buffers land in PSRAM
 */
#include <new>
#include <stdlib.h>
#include <string.h>

#include "imgcore.h"

/* The three headers each define the same helper macros (in slightly different
 * ways); clear them between includes so the compiler doesn't complain. */
#include "JPEGDEC.h"
#undef INTELSHORT
#undef INTELLONG
#undef MOTOSHORT
#undef MOTOLONG
#undef REGISTER_WIDTH
#undef BIGINT
#undef BIGUINT
#include "JPEGENC.h"
#undef INTELSHORT
#undef INTELLONG
#undef MOTOSHORT
#undef MOTOLONG
#undef REGISTER_WIDTH
#undef BIGINT
#undef BIGUINT
#include "PNGdec.h"

#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#endif

/* ------------------------------------------------------------------ memory */

/* Big, mostly-streamed buffers (pixels, output): PSRAM if there is any. */
static void *alloc_big(size_t n) {
#ifdef ESP_PLATFORM
    void *p = heap_caps_malloc(n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (p) return p;
    return heap_caps_malloc(n, MALLOC_CAP_8BIT);
#else
    return malloc(n);
#endif
}

/* Decoder state is hammered on every pixel: internal RAM if it fits. */
static void *alloc_fast(size_t n) {
#ifdef ESP_PLATFORM
    void *p = heap_caps_malloc(n, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (p) return p;
    return heap_caps_malloc(n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
#else
    return malloc(n);
#endif
}

static void mem_free(void *p) {
#ifdef ESP_PLATFORM
    heap_caps_free(p);
#else
    free(p);
#endif
}

extern "C" void img_free(void *p) { mem_free(p); }

/* --------------------------------------------------------------- resampler */
/* Shrinks by averaging: each source pixel falls in exactly one destination
 * cell, and a cell's value is the mean of the pixels that fell in it. Source
 * rows must arrive in order. Source pixels are RGB565, the destination RGB888. */

struct Resampler {
    int cx0, cy0, cw, ch;   /* the part of the source that is used */
    int dw, dh;             /* destination size */
    uint16_t *xmap;         /* source column (within crop) -> destination column */
    uint32_t *xcnt;         /* source pixels per destination column */
    uint32_t *acc;          /* dw * 3 running sums for the current dest row */
    uint8_t *dst;           /* dw * dh * 3 */
    int cur;                /* destination row being accumulated, -1 for none */
    uint32_t rows;          /* source rows added to it */
    int done_rows;          /* dest rows written so far */
};

static void rs_free(Resampler *r) {
    mem_free(r->xmap); mem_free(r->xcnt); mem_free(r->acc); mem_free(r->dst);
    r->xmap = NULL; r->xcnt = NULL; r->acc = NULL; r->dst = NULL;
}

static int rs_init(Resampler *r, int cx0, int cy0, int cw, int ch, int dw, int dh) {
    memset(r, 0, sizeof(*r));
    r->cx0 = cx0; r->cy0 = cy0; r->cw = cw; r->ch = ch; r->dw = dw; r->dh = dh;
    r->cur = -1;
    if (cw < 1 || ch < 1 || dw < 1 || dh < 1 || dw > cw || dh > ch || cw > 65535) return IMG_E_PARAM;
    r->xmap = (uint16_t *)alloc_big(sizeof(uint16_t) * cw);
    r->xcnt = (uint32_t *)alloc_big(sizeof(uint32_t) * dw);
    r->acc = (uint32_t *)alloc_big(sizeof(uint32_t) * dw * 3);
    r->dst = (uint8_t *)alloc_big((size_t)dw * dh * 3);
    if (!r->xmap || !r->xcnt || !r->acc || !r->dst) { rs_free(r); return IMG_E_MEMORY; }
    memset(r->xcnt, 0, sizeof(uint32_t) * dw);
    for (int x = 0; x < cw; x++) {
        int dx = (int)((int64_t)x * dw / cw);
        r->xmap[x] = (uint16_t)dx;
        r->xcnt[dx]++;
    }
    memset(r->acc, 0, sizeof(uint32_t) * dw * 3);
    return IMG_OK;
}

static void rs_flush(Resampler *r) {
    if (r->cur < 0 || r->rows == 0) return;
    uint8_t *o = r->dst + (size_t)r->cur * r->dw * 3;
    for (int dx = 0; dx < r->dw; dx++) {
        uint32_t n = r->xcnt[dx] * r->rows;
        for (int c = 0; c < 3; c++)
            o[dx * 3 + c] = (uint8_t)((r->acc[dx * 3 + c] + n / 2) / n);
    }
    r->done_rows++;
    memset(r->acc, 0, sizeof(uint32_t) * r->dw * 3);
    r->rows = 0;
}

/* row: the whole source row (from column 0) as RGB565 */
static void rs_row(Resampler *r, int sy, const uint16_t *row) {
    if (sy < r->cy0 || sy >= r->cy0 + r->ch) return;
    int dy = (int)((int64_t)(sy - r->cy0) * r->dh / r->ch);
    if (dy != r->cur) { rs_flush(r); r->cur = dy; }
    const uint16_t *p = row + r->cx0;
    uint32_t *a = r->acc;
    const uint16_t *map = r->xmap;
    for (int x = 0; x < r->cw; x++) {
        uint32_t v = p[x];
        uint32_t R = (v >> 11) & 31, G = (v >> 5) & 63, B = v & 31;
        uint32_t *c = a + map[x] * 3;
        c[0] += (R << 3) | (R >> 2);
        c[1] += (G << 2) | (G >> 4);
        c[2] += (B << 3) | (B >> 2);
    }
    r->rows++;
}

static int rs_finish(Resampler *r) {
    rs_flush(r);
    return r->done_rows == r->dh ? IMG_OK : IMG_E_FORMAT; /* short or cut-off picture */
}

/* ------------------------------------------------------- picture geometry */

struct Plan {
    int sw, sh;      /* source size, as stored */
    int orient;      /* EXIF 1..8 */
    int cx0, cy0, cw, ch; /* crop, in source pixels */
    int dw, dh;      /* result size in the stored orientation */
};

/* mode THUMB: centred square crop shrunk to size x size (never enlarged
 * beyond what the picture has... a small picture is scaled down to the
 * square only if it is bigger; smaller ones keep their size so the result
 * can be smaller than asked for). FIT: whole picture, longest side <= size. */
static int make_plan(Plan *p, int sw, int sh, int orient, int mode, int size) {
    if (sw < 1 || sh < 1 || size < 1) return IMG_E_PARAM;
    p->sw = sw; p->sh = sh;
    p->orient = (orient >= 1 && orient <= 8) ? orient : 1;
    if (mode == IMG_THUMB_PNG) {
        int s = sw < sh ? sw : sh;
        p->cw = p->ch = s;
        p->cx0 = (sw - s) / 2;
        p->cy0 = (sh - s) / 2;
        p->dw = p->dh = s < size ? s : size;
    } else {
        p->cx0 = p->cy0 = 0; p->cw = sw; p->ch = sh;
        int ow = p->orient >= 5 ? sh : sw, oh = p->orient >= 5 ? sw : sh;
        int big = ow > oh ? ow : oh;
        int tw = ow, th = oh;
        if (big > size) {
            tw = (int)(((int64_t)ow * size + big / 2) / big);
            th = (int)(((int64_t)oh * size + big / 2) / big);
            if (tw < 1) tw = 1;
            if (th < 1) th = 1;
        }
        p->dw = p->orient >= 5 ? th : tw;
        p->dh = p->orient >= 5 ? tw : th;
    }
    return IMG_OK;
}

/* Rotate/flip an RGB888 picture w x h into a new buffer; the result is h x w
 * for orientations 5..8. orient 1 returns the input unchanged. */
static uint8_t *orient_pixels(uint8_t *src, int w, int h, int orient, int *ow, int *oh) {
    if (orient <= 1) { *ow = w; *oh = h; return src; }
    int tw = orient >= 5 ? h : w, th = orient >= 5 ? w : h;
    uint8_t *dst = (uint8_t *)alloc_big((size_t)tw * th * 3);
    if (!dst) return NULL;
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            int nx, ny;
            switch (orient) {
                case 2: nx = w - 1 - x; ny = y; break;
                case 3: nx = w - 1 - x; ny = h - 1 - y; break;
                case 4: nx = x; ny = h - 1 - y; break;
                case 5: nx = y; ny = x; break;
                case 6: nx = h - 1 - y; ny = x; break;
                case 7: nx = h - 1 - y; ny = w - 1 - x; break;
                default: nx = y; ny = w - 1 - x; break; /* 8 */
            }
            const uint8_t *s = src + ((size_t)y * w + x) * 3;
            uint8_t *d = dst + ((size_t)ny * tw + nx) * 3;
            d[0] = s[0]; d[1] = s[1]; d[2] = s[2];
        }
    }
    *ow = tw; *oh = th;
    return dst;
}

/* ----------------------------------------------------------------- JPEG in */

struct JpegJob {
    const imgio_t *io;
    Resampler *rs;
    uint16_t *strip;     /* one MCU row of decoded pixels, strip_pitch wide */
    int strip_pitch;     /* pixels per strip row */
    int strip_rows;      /* rows the strip can hold */
    int sw, sh;          /* decoded (scaled) picture size */
    int strip_y;         /* picture row of strip row 0, -1 when empty */
    int strip_h;         /* rows in use */
};

static int32_t jread(JPEGFILE *f, uint8_t *buf, int32_t len) {
    const imgio_t *io = (const imgio_t *)f->fHandle;
    int n = io->read(io->ctx, buf, len);
    if (n < 0) return 0;
    f->iPos += n;
    return n;
}

static int32_t jseek(JPEGFILE *f, int32_t pos) {
    const imgio_t *io = (const imgio_t *)f->fHandle;
    if (io->seek(io->ctx, pos) != 0) return 0;
    f->iPos = pos;
    return pos;
}

static void jstrip_flush(JpegJob *j) {
    if (j->strip_y < 0) return;
    for (int r = 0; r < j->strip_h; r++) {
        int y = j->strip_y + r;
        if (y >= j->sh) break;
        rs_row(j->rs, y, j->strip + (size_t)r * j->strip_pitch);
    }
    j->strip_y = -1;
}

static int jdraw(JPEGDRAW *d) {
    JpegJob *j = (JpegJob *)d->pUser;
    if (d->y != j->strip_y) {
        jstrip_flush(j);
        j->strip_y = d->y;
        j->strip_h = d->iHeight < j->strip_rows ? d->iHeight : j->strip_rows;
    }
    int w = d->iWidthUsed;
    if (d->x + w > j->strip_pitch) w = j->strip_pitch - d->x;
    if (w <= 0) return 1;
    for (int r = 0; r < j->strip_h; r++)
        memcpy(j->strip + (size_t)r * j->strip_pitch + d->x, d->pPixels + (size_t)r * d->iWidth, w * 2);
    return 1;
}

static int jpeg_header(JPEGDEC *dec, const imgio_t *io, int *w, int *h, int *orient) {
    /* JPEGDEC reads the 2-byte SOI marker itself; reject anything else early */
    uint8_t m[2];
    if (io->seek(io->ctx, 0) != 0 || io->read(io->ctx, m, 2) != 2) return IMG_E_IO;
    if (m[0] != 0xFF || m[1] != 0xD8) return IMG_E_FORMAT;
    io->seek(io->ctx, 0);
    if (!dec->open((void *)io, io->size, NULL, jread, jseek, jdraw)) {
        int e = dec->getLastError();
        return e == JPEG_UNSUPPORTED_FEATURE ? IMG_E_UNSUPPORTED : IMG_E_FORMAT;
    }
    *w = dec->getWidth();
    *h = dec->getHeight();
    *orient = dec->getOrientation();
    return IMG_OK;
}

static int jpeg_run(const imgio_t *io, int mode, int size, Plan *plan, Resampler *rs) {
    JPEGDEC *dec = (JPEGDEC *)alloc_fast(sizeof(JPEGDEC));
    if (!dec) return IMG_E_MEMORY;
    new (dec) JPEGDEC();
    int w, h, orient;
    int rc = jpeg_header(dec, io, &w, &h, &orient);
    if (rc != IMG_OK) { mem_free(dec); return rc; }
    rc = make_plan(plan, w, h, orient, mode, size);
    if (rc != IMG_OK) { dec->close(); mem_free(dec); return rc; }

    /* decode at the largest reduction that keeps at least the pixels we need */
    int div = 1, opt = 0;
    if (plan->cw / 8 >= plan->dw && plan->ch / 8 >= plan->dh) { div = 8; opt = JPEG_SCALE_EIGHTH; }
    else if (plan->cw / 4 >= plan->dw && plan->ch / 4 >= plan->dh) { div = 4; opt = JPEG_SCALE_QUARTER; }
    else if (plan->cw / 2 >= plan->dw && plan->ch / 2 >= plan->dh) { div = 2; opt = JPEG_SCALE_HALF; }

    JpegJob job;
    memset(&job, 0, sizeof(job));
    job.io = io;
    job.rs = rs;
    job.sw = (w + div - 1) / div;
    job.sh = (h + div - 1) / div;
    job.strip_pitch = job.sw + 16;
    job.strip_rows = 16;
    job.strip_y = -1;
    job.strip = (uint16_t *)alloc_big((size_t)job.strip_pitch * job.strip_rows * 2);
    if (!job.strip) { dec->close(); mem_free(dec); return IMG_E_MEMORY; }

    /* the plan was made on the full size; bring the crop and target to the
       reduced picture. The destination size stays the same. */
    int cx0 = plan->cx0 / div, cy0 = plan->cy0 / div;
    int cw = plan->cw / div, ch = plan->ch / div;
    if (cw > job.sw - cx0) cw = job.sw - cx0;
    if (ch > job.sh - cy0) ch = job.sh - cy0;
    rc = rs_init(rs, cx0, cy0, cw, ch, plan->dw, plan->dh);
    if (rc != IMG_OK) { mem_free(job.strip); dec->close(); mem_free(dec); return rc; }

    dec->setPixelType(RGB565_LITTLE_ENDIAN);
    dec->setUserPointer(&job);
    rc = IMG_OK;
    if (!dec->decode(0, 0, opt)) {
        int e = dec->getLastError();
        rc = e == JPEG_UNSUPPORTED_FEATURE ? IMG_E_UNSUPPORTED : (e == JPEG_ERROR_MEMORY ? IMG_E_MEMORY : IMG_E_FORMAT);
    } else {
        jstrip_flush(&job);
        rc = rs_finish(rs);
    }
    dec->close();
    mem_free(job.strip);
    mem_free(dec);
    if (rc != IMG_OK) rs_free(rs);
    return rc;
}

/* ------------------------------------------------------------------ PNG in */

struct PngJob {
    PNG *png;
    Resampler *rs;
    uint16_t *line;
    int width;
};

static int32_t pread_cb(PNGFILE *f, uint8_t *buf, int32_t len) {
    const imgio_t *io = (const imgio_t *)f->fHandle;
    int n = io->read(io->ctx, buf, len);
    if (n < 0) return 0;
    f->iPos += n;
    return n;
}

static int32_t pseek_cb(PNGFILE *f, int32_t pos) {
    const imgio_t *io = (const imgio_t *)f->fHandle;
    if (io->seek(io->ctx, pos) != 0) return 0;
    f->iPos = pos;
    return pos;
}

static int pdraw(PNGDRAW *d) {
    PngJob *j = (PngJob *)d->pUser;
    if (d->iWidth > j->width) return 0;
    j->png->getLineAsRGB565(d, j->line, PNG_RGB565_LITTLE_ENDIAN, 0x00000000); /* black behind transparency */
    rs_row(j->rs, d->y, j->line);
    return 1;
}

static int png_run(const imgio_t *io, int mode, int size, Plan *plan, Resampler *rs) {
    PNG *png = (PNG *)alloc_fast(sizeof(PNG));
    if (!png) return IMG_E_MEMORY;
    new (png) PNG();
    /* PNG::open() wants a filename + open callback; smuggle the handle through it */
    static const imgio_t *s_io;
    s_io = io;
    struct Opener {
        static void *open(const char *, int32_t *size) { *size = s_io->size; return (void *)s_io; }
        static void close(void *) {}
    };
    io->seek(io->ctx, 0);
    int rc = png->open("", Opener::open, Opener::close, pread_cb, pseek_cb, pdraw);
    if (rc != PNG_SUCCESS) {
        int e = png->getLastError();
        mem_free(png);
        return (e == PNG_UNSUPPORTED_FEATURE || e == PNG_TOO_BIG) ? IMG_E_UNSUPPORTED : IMG_E_FORMAT;
    }
    int w = png->getWidth(), h = png->getHeight();
    rc = make_plan(plan, w, h, 1, mode, size);
    if (rc != IMG_OK) { png->close(); mem_free(png); return rc; }
    rc = rs_init(rs, plan->cx0, plan->cy0, plan->cw, plan->ch, plan->dw, plan->dh);
    if (rc != IMG_OK) { png->close(); mem_free(png); return rc; }

    PngJob job;
    job.png = png; job.rs = rs; job.width = w;
    job.line = (uint16_t *)alloc_big((size_t)w * 2);
    if (!job.line) { rs_free(rs); png->close(); mem_free(png); return IMG_E_MEMORY; }
    int e = png->decode(&job, 0);
    if (e != PNG_SUCCESS) {
        int le = png->getLastError();
        rc = (le == PNG_UNSUPPORTED_FEATURE || le == PNG_TOO_BIG) ? IMG_E_UNSUPPORTED
           : (le == PNG_MEM_ERROR || le == PNG_NO_BUFFER) ? IMG_E_MEMORY : IMG_E_FORMAT;
    } else {
        rc = rs_finish(rs);
    }
    png->close();
    mem_free(job.line);
    mem_free(png);
    if (rc != IMG_OK) rs_free(rs);
    return rc;
}

/* ------------------------------------------------------------- PNG output */
/* An uncompressed ("stored") PNG: big for a photo but the thumbnails are small,
 * and it needs no compressor. 80x80 RGB is 19 KB. */

static uint32_t crc_table[256];
static int crc_ready;

static void crc_init(void) {
    if (crc_ready) return;
    for (uint32_t n = 0; n < 256; n++) {
        uint32_t c = n;
        for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
        crc_table[n] = c;
    }
    crc_ready = 1;
}

static uint32_t crc_update(uint32_t crc, const uint8_t *p, size_t n) {
    while (n--) crc = crc_table[(crc ^ *p++) & 255] ^ (crc >> 8);
    return crc;
}

static void put32(uint8_t *p, uint32_t v) {
    p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v;
}

static uint8_t *chunk(uint8_t *o, const char *type, const uint8_t *data, uint32_t len) {
    put32(o, len);
    memcpy(o + 4, type, 4);
    if (len) memcpy(o + 8, data, len);
    put32(o + 8 + len, crc_update(0xFFFFFFFFu, o + 4, 4 + len) ^ 0xFFFFFFFFu);
    return o + 12 + len;
}

static int encode_png(const uint8_t *rgb, int w, int h, imgout_t *out) {
    crc_init();
    size_t raw = (size_t)h * (1 + (size_t)w * 3);
    size_t nblocks = (raw + 65534) / 65535;
    size_t z = 2 + raw + nblocks * 5 + 4;          /* zlib header, data, block headers, adler */
    size_t total = 8 + 25 + (12 + z) + 12;
    uint8_t *buf = (uint8_t *)alloc_big(total);
    uint8_t *zbuf = (uint8_t *)alloc_big(z);
    if (!buf || !zbuf) { mem_free(buf); mem_free(zbuf); return IMG_E_MEMORY; }

    uint8_t *q = zbuf;
    *q++ = 0x78; *q++ = 0x01;
    uint32_t a = 1, b = 0;                         /* adler32 over the raw data */
    size_t left = raw, row_pos = 0;                /* raw stream = per row: 0 + pixels */
    uint8_t rowbuf[1];                             /* (filter byte) */
    (void)rowbuf;
    size_t src_off = 0, in_row = 0;                /* walk the raw stream lazily */
    while (left) {
        size_t n = left > 65535 ? 65535 : left;
        *q++ = (left == n) ? 1 : 0;                /* BFINAL, stored */
        *q++ = n & 255; *q++ = n >> 8;
        *q++ = ~n & 255; *q++ = (~n >> 8) & 255;
        for (size_t i = 0; i < n; i++) {
            uint8_t v;
            if (in_row == 0) v = 0;                /* filter type: none */
            else v = rgb[src_off++];
            if (++in_row == 1 + (size_t)w * 3) in_row = 0;
            *q++ = v;
            a += v; if (a >= 65521) a -= 65521;
            b += a; if (b >= 65521) b -= 65521;
        }
        left -= n;
    }
    (void)row_pos;
    put32(q, (b << 16) | a); q += 4;

    uint8_t *o = buf;
    static const uint8_t sig[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    memcpy(o, sig, 8); o += 8;
    uint8_t ihdr[13];
    put32(ihdr, w); put32(ihdr + 4, h);
    ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    o = chunk(o, "IHDR", ihdr, 13);
    o = chunk(o, "IDAT", zbuf, (uint32_t)(q - zbuf));
    o = chunk(o, "IEND", NULL, 0);
    mem_free(zbuf);
    out->data = buf;
    out->len = (size_t)(o - buf);
    return IMG_OK;
}

/* ------------------------------------------------------------ JPEG output */

static int encode_jpeg(uint8_t *rgb, int w, int h, int quality, imgout_t *out) {
    /* The encoder reads whole 16x16 blocks, so give it a copy padded to a
       multiple of 16 in both directions by repeating the last column/row.
       It swaps to blue-first on the way: JPEGENC's "RGB888" is BGR in memory. */
    int pw = (w + 15) & ~15, ph = (h + 15) & ~15;
    uint8_t *pad = (uint8_t *)alloc_big((size_t)pw * ph * 3);
    size_t cap = (size_t)w * h * 3 + 8192;       /* generous: even noise at best quality fits */
    uint8_t *buf = (uint8_t *)alloc_big(cap);
    JPEGENC *enc = (JPEGENC *)alloc_fast(sizeof(JPEGENC));
    if (!pad || !buf || !enc) { mem_free(pad); mem_free(buf); mem_free(enc); return IMG_E_MEMORY; }
    for (int y = 0; y < ph; y++) {
        const uint8_t *s = rgb + (size_t)(y < h ? y : h - 1) * w * 3;
        uint8_t *d = pad + (size_t)y * pw * 3;
        for (int x = 0; x < pw; x++) {
            const uint8_t *p = s + (x < w ? x : w - 1) * 3;
            d[x * 3] = p[2]; d[x * 3 + 1] = p[1]; d[x * 3 + 2] = p[0];
        }
    }
    new (enc) JPEGENC();
    uint8_t q = quality >= 90 ? JPEGE_Q_BEST : quality >= 75 ? JPEGE_Q_HIGH : quality >= 55 ? JPEGE_Q_MED : JPEGE_Q_LOW;
    JPEGENCODE je;
    int rc = IMG_OK;
    if (enc->open(buf, (int)cap) != JPEGE_SUCCESS ||
        enc->encodeBegin(&je, w, h, JPEGE_PIXEL_RGB888, JPEGE_SUBSAMPLE_420, q) != JPEGE_SUCCESS ||
        enc->addFrame(&je, pad, pw * 3) != JPEGE_SUCCESS) {
        rc = IMG_E_FORMAT;
    } else {
        int n = enc->close();
        if (n <= 0) rc = IMG_E_FORMAT;
        else { out->data = buf; out->len = (size_t)n; buf = NULL; }
    }
    mem_free(pad);
    mem_free(buf);
    mem_free(enc);
    return rc;
}

/* ------------------------------------------------------------------ public */

static int sniff(const imgio_t *io) {
    uint8_t m[8];
    if (io->seek(io->ctx, 0) != 0) return IMG_E_IO;
    int n = io->read(io->ctx, m, 8);
    if (n < 0) return IMG_E_IO;
    if (n >= 2 && m[0] == 0xFF && m[1] == 0xD8) return 1;
    static const uint8_t png[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    if (n == 8 && memcmp(m, png, 8) == 0) return 2;
    return IMG_E_FORMAT;
}

extern "C" int img_make(const imgio_t *in, int mode, int size, int quality, imgout_t *out) {
    if (!in || !out || size < 1 || (mode != IMG_THUMB_PNG && mode != IMG_FIT_JPEG)) return IMG_E_PARAM;
    memset(out, 0, sizeof(*out));
    int kind = sniff(in);
    if (kind < 0) return kind;

    Plan plan;
    Resampler rs;
    memset(&plan, 0, sizeof(plan));
    int rc = kind == 1 ? jpeg_run(in, mode, size, &plan, &rs) : png_run(in, mode, size, &plan, &rs);
    if (rc != IMG_OK) return rc;

    int ow, oh;
    uint8_t *pix = orient_pixels(rs.dst, rs.dw, rs.dh, plan.orient, &ow, &oh);
    if (!pix) { rs_free(&rs); return IMG_E_MEMORY; }
    rc = mode == IMG_THUMB_PNG ? encode_png(pix, ow, oh, out) : encode_jpeg(pix, ow, oh, quality, out);
    if (pix != rs.dst) mem_free(pix);
    rs_free(&rs);
    if (rc != IMG_OK) return rc;
    out->width = ow; out->height = oh;
    out->src_width = plan.sw; out->src_height = plan.sh;
    return IMG_OK;
}

extern "C" int img_info(const imgio_t *in, int *width, int *height) {
    int kind = sniff(in);
    if (kind < 0) return kind;
    if (kind == 2) {
        uint8_t h[24];
        in->seek(in->ctx, 0);
        if (in->read(in->ctx, h, 24) != 24) return IMG_E_FORMAT;
        *width = (h[16] << 24) | (h[17] << 16) | (h[18] << 8) | h[19];
        *height = (h[20] << 24) | (h[21] << 16) | (h[22] << 8) | h[23];
        return IMG_OK;
    }
    JPEGDEC *dec = (JPEGDEC *)alloc_fast(sizeof(JPEGDEC));
    if (!dec) return IMG_E_MEMORY;
    new (dec) JPEGDEC();
    int o;
    int rc = jpeg_header(dec, in, width, height, &o);
    if (rc == IMG_OK) dec->close();
    mem_free(dec);
    return rc;
}
