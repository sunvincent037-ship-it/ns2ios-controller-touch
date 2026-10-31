#include <assert.h>
#include <string.h>
#include "shell_module_name.h"

int main(void) {
    char out[17] = {0};
    assert(dm_shell_module_name("__dmmainx0", out) == 4);
    assert(!strcmp(out, "main"));
    assert(dm_shell_module_name("__dmsdkx0", out) == 3);
    assert(!strcmp(out, "sdk"));
    assert(dm_shell_module_name("__dm_nro_x0", out) == 0);
    assert(dm_shell_module_name("__dm_nro_x1", out) == 0);
    assert(dm_shell_module_name("__dmmainx2", out) == 0);
    assert(dm_shell_module_name("__text", out) == 0);
    return 0;
}
