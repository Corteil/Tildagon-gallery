/* Memory hooks for the PC tests */
#include <stdlib.h>
#include "../imgcore.h"
void *img_alloc(size_t n) { return malloc(n); }
void img_release(void *p) { free(p); }
