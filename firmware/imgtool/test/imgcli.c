/* Host test driver: imgcli thumb|fit SIZE IN OUT [QUALITY] */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../imgcore.h"
static int rd(void *c, uint8_t *b, int n) { return (int)fread(b, 1, n, (FILE *)c); }
static int sk(void *c, int p) { return fseek((FILE *)c, p, SEEK_SET); }
int main(int argc, char **argv) {
    if (argc < 5) return 2;
    FILE *f = fopen(argv[3], "rb");
    if (!f) { puts("nofile"); return 3; }
    fseek(f, 0, SEEK_END); int n = (int)ftell(f); fseek(f, 0, SEEK_SET);
    imgio_t io = { f, n, rd, sk };
    if (!strcmp(argv[1], "info")) {
        int w, h; int rc = img_info(&io, &w, &h);
        printf("rc=%d %d %d\n", rc, w, h); return rc ? 1 : 0;
    }
    imgout_t o;
    int rc = img_make(&io, strcmp(argv[1], "thumb") ? IMG_FIT_JPEG : IMG_THUMB_PNG, atoi(argv[2]), argc > 5 ? atoi(argv[5]) : 85, &o);
    if (rc) { printf("rc=%d\n", rc); return 1; }
    FILE *g = fopen(argv[4], "wb"); fwrite(o.data, 1, o.len, g); fclose(g);
    printf("rc=0 %dx%d from %dx%d, %zu bytes\n", o.width, o.height, o.src_width, o.src_height, o.len);
    img_free(o.data);
    return 0;
}
