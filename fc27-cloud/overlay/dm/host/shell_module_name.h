#pragma once
#include <stddef.h>
#include <string.h>

// Aggregate NRO sections belong to the loader's NRO table, never boot modules.
static inline size_t dm_shell_module_name(const char *section, char name[17]) {
    size_t length = 0;
    while (length < 16 && section[length]) length++;
    if (length < 7 || strncmp(section, "__dm", 4) ||
        !strncmp(section, "__dm_nro_", 9) ||
        section[length - 2] != 'x' || section[length - 1] != '0') return 0;
    size_t size = length - 6;
    memcpy(name, section + 4, size);
    name[size] = 0;
    return size;
}
