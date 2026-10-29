#pragma once
#include <string.h>

// The renderer already loads demanded libraries and warms its measured PSO
// manifests. Compiling every packaged source before boot is optional: a large
// library can contain tens of thousands of shaders no startup scene uses.
static inline int dm_shader_prep_all(const char *mode) {
    return mode && !strcmp(mode, "all");
}
static inline int dm_shader_prep_workers(int cpus, int requested) {
    int workers = requested > 0 ? requested : cpus - 2;
    return workers < 1 ? 1 : workers > 2 ? 2 : workers;
}
// Foundation thermal states: nominal 0, fair 1, serious 2, critical 3.
static inline int dm_shader_prep_limit(int workers, int thermal, int active, int low_power) {
    if (!active || thermal >= 2) return 0;
    return thermal >= 1 || low_power ? 1 : workers;
}
