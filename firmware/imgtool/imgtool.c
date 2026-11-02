/* MicroPython module `imgtool`: shrink JPEG/PNG files and make thumbnails
 * in native code. Python half: ../../thumbs.py.
 *
 *   imgtool.size(path)                      -> (width, height)
 *   imgtool.thumbnail(src, dst, size=80)    -> (w, h)   square PNG, centre-cropped
 *   imgtool.resize(src, dst, max=480, quality=85) -> (w, h)   JPEG, longest side <= max
 *
 * Errors: ValueError (not a readable JPEG/PNG), NotImplementedError (a kind of
 * JPEG/PNG the decoders can't do: interlaced or 16-bit PNG, arithmetic or
 * lossless JPEG), MemoryError, OSError (file trouble).
 */
#include "py/runtime.h"
#include "py/builtin.h"
#include "py/stream.h"
#include "py/objstr.h"

#include "imgcore.h"

typedef struct {
    mp_obj_t file;
    const mp_stream_p_t *p;
    int err;
} filectx_t;

static int fc_read(void *c, uint8_t *buf, int len) {
    filectx_t *f = (filectx_t *)c;
    int errcode = 0;
    mp_uint_t n = f->p->read(f->file, buf, len, &errcode);
    if (n == MP_STREAM_ERROR) { f->err = errcode; return -1; }
    return (int)n;
}

static int fc_seek(void *c, int pos) {
    filectx_t *f = (filectx_t *)c;
    int errcode = 0;
    mp_off_t r = mp_stream_seek(f->file, pos, MP_SEEK_SET, &errcode);
    if (r == (mp_off_t)-1 || errcode) { f->err = errcode ? errcode : MP_EIO; return -1; }
    return 0;
}

static mp_obj_t open_file(mp_obj_t path, const char *mode) {
    mp_obj_t args[2] = { path, mp_obj_new_str(mode, strlen(mode)) };
    return mp_call_function_n_kw(MP_OBJ_FROM_PTR(&mp_builtin_open_obj), 2, 0, args);
}

/* Opens `path` for reading and finds its length. Raises on failure. */
static void open_in(mp_obj_t path, filectx_t *f, imgio_t *io) {
    f->file = open_file(path, "rb");
    f->p = mp_get_stream_raise(f->file, MP_STREAM_OP_READ | MP_STREAM_OP_IOCTL);
    f->err = 0;
    int errcode = 0;
    mp_off_t end = mp_stream_seek(f->file, 0, MP_SEEK_END, &errcode);
    if (end == (mp_off_t)-1 || errcode) {
        mp_stream_close(f->file);
        mp_raise_OSError(errcode ? errcode : MP_EIO);
    }
    io->ctx = f;
    io->size = (int)end;
    io->read = fc_read;
    io->seek = fc_seek;
}

static NORETURN void raise_for(int rc, filectx_t *f) {
    mp_stream_close(f->file);
    switch (rc) {
        case IMG_E_UNSUPPORTED:
            mp_raise_NotImplementedError(MP_ERROR_TEXT("unsupported image type"));
        case IMG_E_MEMORY:
            mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("image too big for memory"));
        case IMG_E_IO:
            mp_raise_OSError(f->err ? f->err : MP_EIO);
        case IMG_E_PARAM:
            mp_raise_ValueError(MP_ERROR_TEXT("bad size"));
        default:
            if (f->err) mp_raise_OSError(f->err);
            mp_raise_ValueError(MP_ERROR_TEXT("not a readable JPEG or PNG"));
    }
}

static mp_obj_t pair(int a, int b) {
    mp_obj_t t[2] = { MP_OBJ_NEW_SMALL_INT(a), MP_OBJ_NEW_SMALL_INT(b) };
    return mp_obj_new_tuple(2, t);
}

static mp_obj_t imgtool_size(mp_obj_t path) {
    filectx_t f; imgio_t io;
    open_in(path, &f, &io);
    int w = 0, h = 0;
    int rc = img_info(&io, &w, &h);
    if (rc != IMG_OK) raise_for(rc, &f);
    mp_stream_close(f.file);
    return pair(w, h);
}
static MP_DEFINE_CONST_FUN_OBJ_1(imgtool_size_obj, imgtool_size);

static mp_obj_t make(mp_obj_t src, mp_obj_t dst, int mode, int size, int quality) {
    if (size < 1 || size > 4096) mp_raise_ValueError(MP_ERROR_TEXT("size must be 1..4096"));
    filectx_t f; imgio_t io;
    open_in(src, &f, &io);
    imgout_t out;
    int rc = img_make(&io, mode, size, quality, &out);
    if (rc != IMG_OK) raise_for(rc, &f);
    mp_stream_close(f.file);

    /* write the result; nothing here may raise while `out` is allocated */
    nlr_buf_t nlr;
    if (nlr_push(&nlr) == 0) {
        mp_obj_t o = open_file(dst, "wb");
        const mp_stream_p_t *p = mp_get_stream_raise(o, MP_STREAM_OP_WRITE);
        size_t done = 0;
        int errcode = 0;
        while (done < out.len) {
            mp_uint_t n = p->write(o, out.data + done, out.len - done, &errcode);
            if (n == MP_STREAM_ERROR) { mp_stream_close(o); mp_raise_OSError(errcode); }
            done += n;
        }
        mp_stream_close(o);
        nlr_pop();
    } else {
        img_free(out.data);
        nlr_jump(nlr.ret_val);
    }
    img_free(out.data);
    return pair(out.width, out.height);
}

static mp_obj_t imgtool_thumbnail(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_src, ARG_dst, ARG_size };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_src, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_dst, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_size, MP_ARG_INT, { .u_int = 80 } },
    };
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, a);
    return make(a[ARG_src].u_obj, a[ARG_dst].u_obj, IMG_THUMB_PNG, a[ARG_size].u_int, 0);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(imgtool_thumbnail_obj, 2, imgtool_thumbnail);

static mp_obj_t imgtool_resize(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_src, ARG_dst, ARG_max, ARG_quality };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_src, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_dst, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_max, MP_ARG_INT, { .u_int = 480 } },
        { MP_QSTR_quality, MP_ARG_INT, { .u_int = 85 } },
    };
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, a);
    return make(a[ARG_src].u_obj, a[ARG_dst].u_obj, IMG_FIT_JPEG, a[ARG_max].u_int, a[ARG_quality].u_int);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(imgtool_resize_obj, 2, imgtool_resize);

static const mp_rom_map_elem_t imgtool_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_imgtool) },
    { MP_ROM_QSTR(MP_QSTR_size), MP_ROM_PTR(&imgtool_size_obj) },
    { MP_ROM_QSTR(MP_QSTR_thumbnail), MP_ROM_PTR(&imgtool_thumbnail_obj) },
    { MP_ROM_QSTR(MP_QSTR_resize), MP_ROM_PTR(&imgtool_resize_obj) },
};
static MP_DEFINE_CONST_DICT(imgtool_globals, imgtool_globals_table);

const mp_obj_module_t imgtool_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&imgtool_globals,
};

MP_REGISTER_MODULE(MP_QSTR_imgtool, imgtool_module);
