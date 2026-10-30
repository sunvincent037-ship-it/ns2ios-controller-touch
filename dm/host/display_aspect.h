#ifndef DM_DISPLAY_ASPECT_H
#define DM_DISPLAY_ASPECT_H

#include <errno.h>
#include <math.h>
#include <stdlib.h>

// Explicit opt-in only. Invalid or absent values retain the tested 16:9 path.
static inline double dm_display_aspect(const char *value) {
    if (!value || *value < '0' || *value > '9') return 0;
    char *end;
    errno = 0;
    unsigned long width = strtoul(value, &end, 10);
    if (errno || *end != ':' || width < 1 || width > 10000) return 0;
    const char *height_text = end + 1;
    if (*height_text < '0' || *height_text > '9') return 0;
    errno = 0;
    unsigned long height = strtoul(height_text, &end, 10);
    if (errno || *end || height < 1 || height > 10000) return 0;
    double ratio = (double)width / (double)height;
    return ratio >= 0.5 && ratio <= 3.0 ? ratio : 0;
}

// Keep the requested horizontal resolution. Only adapt the measured 16:9
// requests; an already custom-sized viewport and unrelated sizes pass through.
static inline int dm_display_height(int width, int height, double ratio) {
    if (!isfinite(ratio) || ratio < 0.5 || ratio > 3.0 ||
        width < 64 || width > 4096 || height < 64 || height > 4096 ||
        fabs((double)width / height - 16.0 / 9.0) > 0.01) return height;
    double wanted = floor((double)width / ratio + 0.5);
    return wanted >= 64 && wanted <= 4096 ? (int)wanted : height;
}

// Fit uniformly into the available view. This changes neither source UVs nor
// the game's projection: camera framing is a separate device acceptance check.
static inline void dm_display_fit(double *width, double *height, double ratio) {
    if (!width || !height || !isfinite(*width) || !isfinite(*height) ||
        *width <= 0 || *height <= 0) return;
    if (!isfinite(ratio) || ratio < 0.5 || ratio > 3.0) ratio = 16.0 / 9.0;
    if (*width / *height > ratio) *width = *height * ratio;
    else *height = *width / ratio;
}

#endif
