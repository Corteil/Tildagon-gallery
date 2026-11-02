/* The few C library functions the bitbank2 code calls and a MicroPython native
 * module does not get from the firmware. */
#include <stddef.h>

size_t strlen(const char *s) {
    const char *p = s;
    while (*p) p++;
    return (size_t)(p - s);
}

int strcmp(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return (unsigned char)*a - (unsigned char)*b;
}

int memcmp(const void *a, const void *b, size_t n) {
    const unsigned char *p = a, *q = b;
    while (n--) {
        if (*p != *q) return *p - *q;
        p++; q++;
    }
    return 0;
}

/* zlib's allocator hooks. PNGdec gives zlib its own memory, so these are
 * never called; they only have to exist. */
void *zcalloc(void *opaque, unsigned items, unsigned size) { (void)opaque; (void)items; (void)size; return 0; }
void zcfree(void *opaque, void *ptr) { (void)opaque; (void)ptr; }

/* Older MicroPython trees (such as 1.28) don't link memcpy/memset/memmove into
 * native modules; newer ones do. Define them here so the module builds against
 * either. Copying a word at a time when both ends are aligned. */
void *memset(void *s, int c, size_t n) {
    unsigned char *p = s;
    while (n && ((size_t)p & 3)) { *p++ = (unsigned char)c; n--; }
    {
        unsigned int w = (unsigned char)c;
        unsigned int *q;
        w |= w << 8; w |= w << 16;
        q = (unsigned int *)p;
        while (n >= 4) { *q++ = w; n -= 4; }
        p = (unsigned char *)q;
    }
    while (n--) *p++ = (unsigned char)c;
    return s;
}

void *memmove(void *dst, const void *src, size_t n) {
    unsigned char *d = dst;
    const unsigned char *s = src;
    if (d == s || n == 0) return dst;
    if (d < s || d >= s + n) {  /* copy forwards */
        if ((((size_t)d | (size_t)s) & 3) == 0) {
            unsigned int *dw = (unsigned int *)d;
            const unsigned int *sw = (const unsigned int *)s;
            while (n >= 4) { *dw++ = *sw++; n -= 4; }
            d = (unsigned char *)dw; s = (const unsigned char *)sw;
        }
        while (n--) *d++ = *s++;
    } else {                    /* overlapping, copy backwards */
        d += n; s += n;
        while (n--) *--d = *--s;
    }
    return dst;
}

void *memcpy(void *dst, const void *src, size_t n) { return memmove(dst, src, n); }
