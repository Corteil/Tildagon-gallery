/* imgcore: see imgcore.h. Plain C, 32-bit integer maths only (no 64-bit
 * division, no floats), no writable statics: it has to link as a MicroPython
 * native module, which supports neither a C library nor initialised data.
 *
 * Needs, from the build: img_alloc / img_release, and the three bitbank2
 * libraries compiled as C (lib_jpegdec.c, lib_pngdec.c, lib_jpegenc.c).
 */
#include <stdint.h>
#include <string.h>

#include "imgcore.h"

/* The three headers define some of the same helper macros; clear them between
 * includes so each library sees its own. */
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

/* The libraries' internals that their C headers don't expose; lib_*.c do */
int img_jpeg_init(JPEGIMAGE *p);
int img_jpeg_decode(JPEGIMAGE *p, int opts);
int img_png_init(PNGIMAGE *p);
int img_png_decode(PNGIMAGE *p, void *user, int opts);
void img_png_rgb565(PNGDRAW *d, uint16_t *px, int endian, uint32_t bkgd, int alpha);
int img_jpeg_add_frame(JPEGE_IMAGE *p, JPEGENCODE *e, uint8_t *px, int pitch);

void img_free(void *p) { img_release(p); }

/* ------------------------------------------------------------- resampler */
/* Shrinks by averaging: each source pixel falls in exactly one destination
 * cell, and a cell's value is the mean of the pixels that fell in it. Source
 * rows must arrive in order. Source pixels are RGB565, the destination RGB888. */

typedef struct {
    int cx0, cy0, cw, ch;   /* the part of the source that is used */
    int dw, dh;             /* destination size */
    uint16_t *xmap;         /* source column (within crop) -> destination column */
    uint32_t *xcnt;         /* source pixels per destination column */
    uint32_t *acc;          /* dw * 3 running sums for the current dest row */
    uint8_t *dst;           /* dw * dh * 3 */
    int cur;                /* destination row being accumulated, -1 for none */
    uint32_t rows;          /* source rows added to it */
    int done_rows;          /* dest rows written so far */
} Resampler;

static void rs_free(Resampler *r) {
    img_release(r->xmap); img_release(r->xcnt); img_release(r->acc); img_release(r->dst);
    r->xmap = NULL; r->xcnt = NULL; r->acc = NULL; r->dst = NULL;
}

static int rs_init(Resampler *r, int cx0, int cy0, int cw, int ch, int dw, int dh) {
    int x;
    memset(r, 0, sizeof(*r));
    r->cx0 = cx0; r->cy0 = cy0; r->cw = cw; r->ch = ch; r->dw = dw; r->dh = dh;
    r->cur = -1;
    if (cw < 1 || ch < 1 || dw < 1 || dh < 1 || dw > cw || dh > ch || cw > 65535) return IMG_E_PARAM;
    r->xmap = (uint16_t *)img_alloc(sizeof(uint16_t) * cw);
    r->xcnt = (uint32_t *)img_alloc(sizeof(uint32_t) * dw);
    r->acc = (uint32_t *)img_alloc(sizeof(uint32_t) * dw * 3);
    r->dst = (uint8_t *)img_alloc((size_t)dw * dh * 3);
    if (!r->xmap || !r->xcnt || !r->acc || !r->dst) { rs_free(r); return IMG_E_MEMORY; }
    memset(r->xcnt, 0, sizeof(uint32_t) * dw);
    for (x = 0; x < cw; x++) {
        int dx = (int)((uint32_t)x * (uint32_t)dw / (uint32_t)cw);  /* x < 2^16, dw <= 2^12 */
        r->xmap[x] = (uint16_t)dx;
        r->xcnt[dx]++;
    }
    memset(r->acc, 0, sizeof(uint32_t) * dw * 3);
    return IMG_OK;
}

static void rs_flush(Resampler *r) {
    uint8_t *o;
    int dx, c;
    if (r->cur < 0 || r->rows == 0) return;
    o = r->dst + (size_t)r->cur * r->dw * 3;
    for (dx = 0; dx < r->dw; dx++) {
        uint32_t n = r->xcnt[dx] * r->rows;
        for (c = 0; c < 3; c++)
            o[dx * 3 + c] = (uint8_t)((r->acc[dx * 3 + c] + n / 2) / n);
    }
    r->done_rows++;
    memset(r->acc, 0, sizeof(uint32_t) * r->dw * 3);
    r->rows = 0;
}

/* row: the whole source row (from column 0) as RGB565 */
static void rs_row(Resampler *r, int sy, const uint16_t *row) {
    int dy, x;
    const uint16_t *p;
    uint32_t *a;
    const uint16_t *map;
    if (sy < r->cy0 || sy >= r->cy0 + r->ch) return;
    dy = (int)((uint32_t)(sy - r->cy0) * (uint32_t)r->dh / (uint32_t)r->ch);  /* both < 2^16 */
    if (dy != r->cur) { rs_flush(r); r->cur = dy; }
    p = row + r->cx0;
    a = r->acc;
    map = r->xmap;
    for (x = 0; x < r->cw; x++) {
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

/* ------------------------------------------------------ picture geometry */

typedef struct {
    int sw, sh;      /* source size, as stored */
    int orient;      /* EXIF 1..8 */
    int cx0, cy0, cw, ch; /* crop, in source pixels */
    int dw, dh;      /* result size in the stored orientation */
} Plan;

/* THUMB: centred square crop shrunk to size x size; a picture smaller than that
 * keeps its size. FIT: whole picture, longest side <= size, never enlarged. */
static int make_plan(Plan *p, int sw, int sh, int orient, int mode, int size) {
    if (sw < 1 || sh < 1 || size < 1 || size > 4096 || sw > 65535 || sh > 65535) return IMG_E_PARAM;
    p->sw = sw; p->sh = sh;
    p->orient = (orient >= 1 && orient <= 8) ? orient : 1;
    if (mode == IMG_THUMB_PNG) {
        int s = sw < sh ? sw : sh;
        p->cw = p->ch = s;
        p->cx0 = (sw - s) / 2;
        p->cy0 = (sh - s) / 2;
        p->dw = p->dh = s < size ? s : size;
    } else {
        int ow = p->orient >= 5 ? sh : sw, oh = p->orient >= 5 ? sw : sh;
        int big = ow > oh ? ow : oh;
        int tw = ow, th = oh;
        p->cx0 = p->cy0 = 0; p->cw = sw; p->ch = sh;
        if (big > size) {
            tw = (int)(((uint32_t)ow * (uint32_t)size + (uint32_t)big / 2) / (uint32_t)big);  /* < 2^28 */
            th = (int)(((uint32_t)oh * (uint32_t)size + (uint32_t)big / 2) / (uint32_t)big);
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
    int tw, th, x, y;
    uint8_t *dst;
    if (orient <= 1) { *ow = w; *oh = h; return src; }
    tw = orient >= 5 ? h : w;
    th = orient >= 5 ? w : h;
    dst = (uint8_t *)img_alloc((size_t)tw * th * 3);
    if (!dst) return NULL;
    for (y = 0; y < h; y++) {
        for (x = 0; x < w; x++) {
            int nx, ny;
            const uint8_t *s;
            uint8_t *d;
            switch (orient) {
                case 2: nx = w - 1 - x; ny = y; break;
                case 3: nx = w - 1 - x; ny = h - 1 - y; break;
                case 4: nx = x; ny = h - 1 - y; break;
                case 5: nx = y; ny = x; break;
                case 6: nx = h - 1 - y; ny = x; break;
                case 7: nx = h - 1 - y; ny = w - 1 - x; break;
                default: nx = y; ny = w - 1 - x; break; /* 8 */
            }
            s = src + ((size_t)y * w + x) * 3;
            d = dst + ((size_t)ny * tw + nx) * 3;
            d[0] = s[0]; d[1] = s[1]; d[2] = s[2];
        }
    }
    *ow = tw; *oh = th;
    return dst;
}

/* ---------------------------------------------------------------- JPEG in */

typedef struct {
    const imgio_t *io;
    Resampler *rs;
    uint16_t *strip;     /* one MCU row of decoded pixels, strip_pitch wide */
    int strip_pitch;     /* pixels per strip row */
    int strip_rows;      /* rows the strip can hold */
    int sw, sh;          /* decoded (scaled) picture size */
    int strip_y;         /* picture row of strip row 0, -1 when empty */
    int strip_h;         /* rows in use */
} JpegJob;

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
    int r;
    if (j->strip_y < 0) return;
    for (r = 0; r < j->strip_h; r++) {
        int y = j->strip_y + r;
        if (y >= j->sh) break;
        rs_row(j->rs, y, j->strip + (size_t)r * j->strip_pitch);
    }
    j->strip_y = -1;
}

static int jdraw(JPEGDRAW *d) {
    JpegJob *j = (JpegJob *)d->pUser;
    int w, r;
    if (d->y != j->strip_y) {
        jstrip_flush(j);
        j->strip_y = d->y;
        j->strip_h = d->iHeight < j->strip_rows ? d->iHeight : j->strip_rows;
    }
    w = d->iWidthUsed;
    if (d->x + w > j->strip_pitch) w = j->strip_pitch - d->x;
    if (w <= 0) return 1;
    for (r = 0; r < j->strip_h; r++)
        memcpy(j->strip + (size_t)r * j->strip_pitch + d->x, d->pPixels + (size_t)r * d->iWidth, w * 2);
    return 1;
}

static int jpeg_open(JPEGIMAGE *dec, const imgio_t *io, int *w, int *h, int *orient) {
    uint8_t m[2];
    int e;
    if (io->seek(io->ctx, 0) != 0 || io->read(io->ctx, m, 2) != 2) return IMG_E_IO;
    if (m[0] != 0xFF || m[1] != 0xD8) return IMG_E_FORMAT;
    io->seek(io->ctx, 0);
    memset(dec, 0, sizeof(*dec));
    dec->pfnRead = jread;
    dec->pfnSeek = jseek;
    dec->pfnDraw = jdraw;
    dec->iMaxMCUs = 1000;
    dec->JPEGFile.iSize = io->size;
    dec->JPEGFile.fHandle = (void *)io;
    if (!img_jpeg_init(dec)) {
        e = dec->iError;
        return e == JPEG_UNSUPPORTED_FEATURE ? IMG_E_UNSUPPORTED : IMG_E_FORMAT;
    }
    *w = dec->iWidth;
    *h = dec->iHeight;
    *orient = (int)dec->ucOrientation;
    return IMG_OK;
}

static int jpeg_run(const imgio_t *io, int mode, int size, Plan *plan, Resampler *rs) {
    JPEGIMAGE *dec = (JPEGIMAGE *)img_alloc(sizeof(JPEGIMAGE));
    JpegJob job;
    int w, h, orient, rc, div = 1, opt = 0, cx0, cy0, cw, ch;
    if (!dec) return IMG_E_MEMORY;
    rc = jpeg_open(dec, io, &w, &h, &orient);
    if (rc != IMG_OK) { img_release(dec); return rc; }
    rc = make_plan(plan, w, h, orient, mode, size);
    if (rc != IMG_OK) { img_release(dec); return rc; }

    /* decode at the largest reduction that keeps at least the pixels we need */
    if (plan->cw / 8 >= plan->dw && plan->ch / 8 >= plan->dh) { div = 8; opt = JPEG_SCALE_EIGHTH; }
    else if (plan->cw / 4 >= plan->dw && plan->ch / 4 >= plan->dh) { div = 4; opt = JPEG_SCALE_QUARTER; }
    else if (plan->cw / 2 >= plan->dw && plan->ch / 2 >= plan->dh) { div = 2; opt = JPEG_SCALE_HALF; }

    memset(&job, 0, sizeof(job));
    job.io = io;
    job.rs = rs;
    job.sw = (w + div - 1) / div;
    job.sh = (h + div - 1) / div;
    job.strip_pitch = job.sw + 16;
    job.strip_rows = 16;
    job.strip_y = -1;
    job.strip = (uint16_t *)img_alloc((size_t)job.strip_pitch * job.strip_rows * 2);
    if (!job.strip) { img_release(dec); return IMG_E_MEMORY; }

    /* the plan was made on the full size; bring the crop to the reduced
       picture. The destination size stays the same. */
    cx0 = plan->cx0 / div; cy0 = plan->cy0 / div;
    cw = plan->cw / div; ch = plan->ch / div;
    if (cw > job.sw - cx0) cw = job.sw - cx0;
    if (ch > job.sh - cy0) ch = job.sh - cy0;
    rc = rs_init(rs, cx0, cy0, cw, ch, plan->dw, plan->dh);
    if (rc != IMG_OK) { img_release(job.strip); img_release(dec); return rc; }

    dec->ucPixelType = RGB565_LITTLE_ENDIAN;
    dec->pUser = &job;
    if (!img_jpeg_decode(dec, opt)) {
        int e = dec->iError;
        rc = e == JPEG_UNSUPPORTED_FEATURE ? IMG_E_UNSUPPORTED : (e == JPEG_ERROR_MEMORY ? IMG_E_MEMORY : IMG_E_FORMAT);
    } else {
        jstrip_flush(&job);
        rc = rs_finish(rs);
    }
    img_release(job.strip);
    img_release(dec);
    if (rc != IMG_OK) rs_free(rs);
    return rc;
}

/* ----------------------------------------------------------------- PNG in */

typedef struct {
    Resampler *rs;
    uint16_t *line;
    int width;
    int hasalpha;
} PngJob;

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
    img_png_rgb565(d, j->line, PNG_RGB565_LITTLE_ENDIAN, 0x00000000, j->hasalpha); /* black behind transparency */
    rs_row(j->rs, d->y, j->line);
    return 1;
}

static int png_run(const imgio_t *io, int mode, int size, Plan *plan, Resampler *rs) {
    PNGIMAGE *png = (PNGIMAGE *)img_alloc(sizeof(PNGIMAGE));
    PngJob job;
    int w, h, rc, e;
    if (!png) return IMG_E_MEMORY;
    memset(png, 0, sizeof(*png));
    io->seek(io->ctx, 0);
    png->pfnRead = pread_cb;
    png->pfnSeek = pseek_cb;
    png->pfnDraw = pdraw;
    png->PNGFile.iSize = io->size;
    png->PNGFile.fHandle = (void *)io;
    if (img_png_init(png) != PNG_SUCCESS) {
        e = png->iError;
        img_release(png);
        return (e == PNG_UNSUPPORTED_FEATURE || e == PNG_TOO_BIG) ? IMG_E_UNSUPPORTED : IMG_E_FORMAT;
    }
    w = png->iWidth; h = png->iHeight;
    rc = make_plan(plan, w, h, 1, mode, size);
    if (rc != IMG_OK) { img_release(png); return rc; }
    rc = rs_init(rs, plan->cx0, plan->cy0, plan->cw, plan->ch, plan->dw, plan->dh);
    if (rc != IMG_OK) { img_release(png); return rc; }

    job.rs = rs; job.width = w; job.hasalpha = png->iHasAlpha;
    job.line = (uint16_t *)img_alloc((size_t)w * 2);
    if (!job.line) { rs_free(rs); img_release(png); return IMG_E_MEMORY; }
    if (img_png_decode(png, &job, 0) != PNG_SUCCESS) {
        e = png->iError;
        rc = (e == PNG_UNSUPPORTED_FEATURE || e == PNG_TOO_BIG) ? IMG_E_UNSUPPORTED
           : (e == PNG_MEM_ERROR || e == PNG_NO_BUFFER) ? IMG_E_MEMORY : IMG_E_FORMAT;
    } else {
        rc = rs_finish(rs);
    }
    img_release(job.line);
    img_release(png);
    if (rc != IMG_OK) rs_free(rs);
    return rc;
}

/* ------------------------------------------------------------- PNG output */
/* An uncompressed ("stored") PNG: big for a photo but the thumbnails are small,
 * and it needs no compressor. 80x80 RGB is 19 KB. */

static uint32_t crc_update(const uint32_t *table, uint32_t crc, const uint8_t *p, size_t n) {
    while (n--) crc = table[(crc ^ *p++) & 255] ^ (crc >> 8);
    return crc;
}

static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}

static uint8_t *chunk(const uint32_t *table, uint8_t *o, const char *type, const uint8_t *data, uint32_t len) {
    put32(o, len);
    memcpy(o + 4, type, 4);
    if (len) memcpy(o + 8, data, len);
    put32(o + 8 + len, crc_update(table, 0xFFFFFFFFu, o + 4, 4 + len) ^ 0xFFFFFFFFu);
    return o + 12 + len;
}

static int encode_png(const uint8_t *rgb, int w, int h, imgout_t *out) {
    static const uint8_t sig[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    uint32_t *table = (uint32_t *)img_alloc(256 * sizeof(uint32_t));  /* CRC table: no writable statics allowed */
    size_t raw = (size_t)h * (1 + (size_t)w * 3);
    size_t nblocks = (raw + 65534) / 65535;
    size_t z = 2 + raw + nblocks * 5 + 4;          /* zlib header, data, block headers, adler */
    size_t total = 8 + 25 + (12 + z) + 12;
    uint8_t *buf = (uint8_t *)img_alloc(total);
    uint8_t *zbuf = (uint8_t *)img_alloc(z);
    uint8_t *q, *o;
    uint8_t ihdr[13];
    uint32_t a = 1, b = 0, n32;
    size_t left = raw, src_off = 0, in_row = 0, row_len = 1 + (size_t)w * 3;
    if (!table || !buf || !zbuf) { img_release(table); img_release(buf); img_release(zbuf); return IMG_E_MEMORY; }
    for (n32 = 0; n32 < 256; n32++) {
        uint32_t c = n32;
        int k;
        for (k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
        table[n32] = c;
    }
    q = zbuf;
    *q++ = 0x78; *q++ = 0x01;
    while (left) {
        size_t n = left > 65535 ? 65535 : left, i;
        *q++ = (left == n) ? 1 : 0;                /* BFINAL, stored */
        *q++ = (uint8_t)(n & 255); *q++ = (uint8_t)(n >> 8);
        *q++ = (uint8_t)(~n & 255); *q++ = (uint8_t)((~n >> 8) & 255);
        for (i = 0; i < n; i++) {
            uint8_t v;
            if (in_row == 0) v = 0;                /* filter type: none */
            else v = rgb[src_off++];
            if (++in_row == row_len) in_row = 0;
            *q++ = v;
            a += v; if (a >= 65521) a -= 65521;
            b += a; if (b >= 65521) b -= 65521;
        }
        left -= n;
    }
    put32(q, (b << 16) | a); q += 4;

    o = buf;
    memcpy(o, sig, 8); o += 8;
    put32(ihdr, (uint32_t)w); put32(ihdr + 4, (uint32_t)h);
    ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    o = chunk(table, o, "IHDR", ihdr, 13);
    o = chunk(table, o, "IDAT", zbuf, (uint32_t)(q - zbuf));
    o = chunk(table, o, "IEND", NULL, 0);
    img_release(zbuf);
    img_release(table);
    out->data = buf;
    out->len = (size_t)(o - buf);
    return IMG_OK;
}

/* ------------------------------------------------------------ JPEG output */

/* Takes ownership of the picture (*rgbp) and releases it as soon as the padded
 * copy exists, so the peak memory is about two pictures, not three. */
static int encode_jpeg(uint8_t **rgbp, int w, int h, int quality, imgout_t *out) {
    uint8_t *rgb = *rgbp;
    /* The encoder reads whole 16x16 blocks, so give it a copy padded to a
       multiple of 16 in both directions by repeating the last column/row.
       It swaps to blue-first on the way: JPEGENC's "RGB888" is BGR in memory. */
    int pw = (w + 15) & ~15, ph = (h + 15) & ~15, x, y, rc = IMG_E_MEMORY, attempt;
    int inplace = (pw == w && ph == h);  /* already whole blocks: swap colours where it is */
    uint8_t *pad = inplace ? rgb : (uint8_t *)img_alloc((size_t)pw * ph * 3);
    JPEGE_IMAGE *enc = (JPEGE_IMAGE *)img_alloc(sizeof(JPEGE_IMAGE));
    uint8_t q = quality >= 90 ? JPEGE_Q_BEST : quality >= 75 ? JPEGE_Q_HIGH : quality >= 55 ? JPEGE_Q_MED : JPEGE_Q_LOW;
    if (!pad || !enc) { if (!inplace) img_release(pad); img_release(enc); return IMG_E_MEMORY; }
    if (inplace) {
        for (y = 0; y < w * h * 3; y += 3) { uint8_t t = pad[y]; pad[y] = pad[y + 2]; pad[y + 2] = t; }
    } else {
        for (y = 0; y < ph; y++) {
            const uint8_t *s = rgb + (size_t)(y < h ? y : h - 1) * w * 3;
            uint8_t *d = pad + (size_t)y * pw * 3;
            for (x = 0; x < pw; x++) {
                const uint8_t *p = s + (x < w ? x : w - 1) * 3;
                d[x * 3] = p[2]; d[x * 3 + 1] = p[1]; d[x * 3 + 2] = p[0];
            }
        }
        img_release(rgb);
        *rgbp = NULL;
    }
    /* Try an output buffer of half the raw size, which is plenty for any
       picture that has been shrunk; if the encoder runs out, try the full size. */
    for (attempt = 0; attempt < 2 && rc == IMG_E_MEMORY; attempt++) {
        size_t cap = (attempt ? (size_t)w * h * 3 : (size_t)w * h * 3 / 2) + 8192;
        uint8_t *buf;
        JPEGENCODE je;
        buf = (uint8_t *)img_alloc(cap);
        if (!buf) break;
        memset(enc, 0, sizeof(*enc));
        enc->pOutput = buf;
        enc->iBufferSize = (int)cap;
        enc->pHighWater = &buf[cap - 512];
        if (JPEGEncodeBegin(enc, &je, w, h, JPEGE_PIXEL_RGB888, JPEGE_SUBSAMPLE_420, q) != JPEGE_SUCCESS) {
            rc = IMG_E_FORMAT;
        } else if (img_jpeg_add_frame(enc, &je, pad, pw * 3) != JPEGE_SUCCESS) {
            rc = enc->iError == JPEGE_NO_BUFFER ? IMG_E_MEMORY : IMG_E_FORMAT;  /* out of room: go round again */
        } else {
            int n = JPEGEncodeEnd(enc);
            if (n <= 0) rc = IMG_E_FORMAT;
            else { out->data = buf; out->len = (size_t)n; buf = NULL; rc = IMG_OK; }
        }
        img_release(buf);
    }
    if (!inplace) img_release(pad);
    img_release(enc);
    return rc;
}

/* ----------------------------------------------------------------- public */

static int sniff(const imgio_t *io) {
    static const uint8_t png[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    uint8_t m[8];
    int n, i;
    if (io->seek(io->ctx, 0) != 0) return IMG_E_IO;
    n = io->read(io->ctx, m, 8);
    if (n < 0) return IMG_E_IO;
    if (n >= 2 && m[0] == 0xFF && m[1] == 0xD8) return 1;
    if (n == 8) {
        for (i = 0; i < 8 && m[i] == png[i]; i++) {}
        if (i == 8) return 2;
    }
    return IMG_E_FORMAT;
}

int img_make(const imgio_t *in, int mode, int size, int quality, imgout_t *out) {
    Plan plan;
    Resampler rs;
    int kind, rc, ow, oh;
    uint8_t *pix;
    if (!in || !out || size < 1 || (mode != IMG_THUMB_PNG && mode != IMG_FIT_JPEG)) return IMG_E_PARAM;
    memset(out, 0, sizeof(*out));
    kind = sniff(in);
    if (kind < 0) return kind;
    memset(&plan, 0, sizeof(plan));
    rc = kind == 1 ? jpeg_run(in, mode, size, &plan, &rs) : png_run(in, mode, size, &plan, &rs);
    if (rc != IMG_OK) return rc;

    pix = orient_pixels(rs.dst, rs.dw, rs.dh, plan.orient, &ow, &oh);
    if (!pix) { rs_free(&rs); return IMG_E_MEMORY; }
    if (pix != rs.dst) { img_release(rs.dst); rs.dst = NULL; }  /* only the rotated copy is needed now */
    if (mode == IMG_THUMB_PNG) {
        rc = encode_png(pix, ow, oh, out);
    } else {
        int same = (pix == rs.dst);
        rc = encode_jpeg(&pix, ow, oh, quality, out);
        if (pix == NULL && same) rs.dst = NULL;  /* encode_jpeg released it */
    }
    if (pix && pix != rs.dst) img_release(pix);
    rs_free(&rs);
    if (rc != IMG_OK) return rc;
    out->width = ow; out->height = oh;
    out->src_width = plan.sw; out->src_height = plan.sh;
    return IMG_OK;
}

int img_info(const imgio_t *in, int *width, int *height) {
    int kind = sniff(in), rc, o;
    if (kind < 0) return kind;
    if (kind == 2) {
        uint8_t h[24];
        in->seek(in->ctx, 0);
        if (in->read(in->ctx, h, 24) != 24) return IMG_E_FORMAT;
        *width = (h[16] << 24) | (h[17] << 16) | (h[18] << 8) | h[19];
        *height = (h[20] << 24) | (h[21] << 16) | (h[22] << 8) | h[23];
        return IMG_OK;
    } else {
        JPEGIMAGE *dec = (JPEGIMAGE *)img_alloc(sizeof(JPEGIMAGE));
        if (!dec) return IMG_E_MEMORY;
        rc = jpeg_open(dec, in, width, height, &o);
        img_release(dec);
        return rc;
    }
}
