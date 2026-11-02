/* _imgtool: native MicroPython module (loaded from a .mpy, no firmware change).
 * Does the pixel work; imgtool.py (the Python half) does the file handling.
 *
 *   _imgtool.make(readinto, seek, size, buf, mode, n, quality)
 *       -> (data, width, height, source_width, source_height)
 *   _imgtool.info(readinto, seek, size, buf) -> (width, height)
 *
 * readinto(buf) and seek(pos) are the methods of an open binary file; size is
 * the file's length; buf is a bytearray used for reading in chunks.
 * mode 0: centre-cropped n x n PNG; mode 1: JPEG with longest side <= n.
 * Raises ValueError, NotImplementedError or MemoryError; errors from the file
 * methods pass straight through.
 */
#include "py/dynruntime.h"
#include "imgcore.h"

/* memory comes from the MicroPython heap (PSRAM on the badge) */
void *img_alloc(size_t n) { return m_malloc(n); }
void img_release(void *p) { if (p) m_free(p); }

typedef struct {
    mp_obj_t readinto, seek, buf;
    uint8_t *bytes;
    size_t cap;
    int cur;      /* where the decoder is in the file */
    int fpos;     /* where the file object is */
    int bstart;   /* file position of bytes[0] */
    int bhave;    /* valid bytes in the buffer */
} reader_t;

static int rd_read(void *c, uint8_t *dst, int len) {
    reader_t *r = (reader_t *)c;
    int total = 0;
    while (len > 0) {
        if (r->cur < r->bstart || r->cur >= r->bstart + r->bhave) {
            mp_obj_t n_obj;
            int n;
            if (r->cur != r->fpos) {
                mp_obj_t pos = mp_obj_new_int(r->cur);
                mp_call_function_n_kw(r->seek, 1, 0, &pos);
                r->fpos = r->cur;
            }
            n_obj = mp_call_function_n_kw(r->readinto, 1, 0, &r->buf);
            n = (n_obj == mp_const_none) ? 0 : (int)mp_obj_get_int(n_obj);
            r->bstart = r->fpos;
            r->bhave = n;
            r->fpos += n;
            if (n <= 0) break;
        }
        {
            int off = r->cur - r->bstart, n = r->bhave - off;
            if (n > len) n = len;
            memcpy(dst, r->bytes + off, n);
            dst += n; len -= n; total += n; r->cur += n;
        }
    }
    return total;
}

static int rd_seek(void *c, int pos) {
    ((reader_t *)c)->cur = pos;  /* lazy: the file is only moved when data is wanted */
    return 0;
}

static void reader_init(reader_t *r, imgio_t *io, mp_obj_t readinto, mp_obj_t seek, mp_obj_t size, mp_obj_t buf) {
    mp_buffer_info_t bi;
    mp_get_buffer_raise(buf, &bi, MP_BUFFER_RW);
    if (bi.len < 512) mp_raise_ValueError("buffer too small");
    r->readinto = readinto; r->seek = seek; r->buf = buf;
    r->bytes = (uint8_t *)bi.buf; r->cap = bi.len;
    r->cur = 0; r->fpos = 0; r->bstart = 0; r->bhave = 0;
    io->ctx = r;
    io->size = (int)mp_obj_get_int(size);
    io->read = rd_read;
    io->seek = rd_seek;
}

static void raise_for(int rc) {
    switch (rc) {
        case IMG_E_UNSUPPORTED: mp_raise_NotImplementedError("unsupported image type");
        case IMG_E_MEMORY: mp_fun_table.raise_msg(mp_fun_table.load_global(MP_QSTR_MemoryError), "image too big for memory");
        case IMG_E_PARAM: mp_raise_ValueError("bad size");
        default: mp_raise_ValueError("not a readable JPEG or PNG");
    }
}

static mp_obj_t imgtool_make(size_t n_args, const mp_obj_t *args) {
    reader_t r;
    imgio_t io;
    imgout_t out;
    mp_obj_t items[5];
    int rc;
    (void)n_args;
    reader_init(&r, &io, args[0], args[1], args[2], args[3]);
    rc = img_make(&io, (int)mp_obj_get_int(args[4]), (int)mp_obj_get_int(args[5]), (int)mp_obj_get_int(args[6]), &out);
    if (rc != IMG_OK) raise_for(rc);
    items[0] = mp_obj_new_bytes(out.data, out.len);
    items[1] = mp_obj_new_int(out.width);
    items[2] = mp_obj_new_int(out.height);
    items[3] = mp_obj_new_int(out.src_width);
    items[4] = mp_obj_new_int(out.src_height);
    img_free(out.data);
    return mp_obj_new_tuple(5, items);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(imgtool_make_obj, 7, 7, imgtool_make);

static mp_obj_t imgtool_info(size_t n_args, const mp_obj_t *args) {
    reader_t r;
    imgio_t io;
    mp_obj_t items[2];
    int w = 0, h = 0, rc;
    (void)n_args;
    reader_init(&r, &io, args[0], args[1], args[2], args[3]);
    rc = img_info(&io, &w, &h);
    if (rc != IMG_OK) raise_for(rc);
    items[0] = mp_obj_new_int(w);
    items[1] = mp_obj_new_int(h);
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(imgtool_info_obj, 4, 4, imgtool_info);

mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    MP_DYNRUNTIME_INIT_ENTRY
    mp_store_global(MP_QSTR___name__, MP_OBJ_NEW_QSTR(MP_QSTR__imgtool));
    mp_store_global(MP_QSTR_make, MP_OBJ_FROM_PTR(&imgtool_make_obj));
    mp_store_global(MP_QSTR_info, MP_OBJ_FROM_PTR(&imgtool_info_obj));
    MP_DYNRUNTIME_INIT_EXIT
}
