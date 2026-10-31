#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Offline-reviewed candidate, exact main fb81983a... only. The engine already
 * implements forced swapchain sizes; use those fields before it creates or
 * resizes its swapchain, so its downstream view/aspect path sees the new size.
 * This does not establish live screen, UI, or camera acceptance. */
typedef int (*fc27_read_fn)(void *, uint64_t, void *, size_t);
typedef void (*fc27_write_fn)(void *, uint64_t, const void *, size_t);
enum { FC27_DISPLAY_REJECT = -1, FC27_DISPLAY_PENDING = 0,
       FC27_DISPLAY_UNCHANGED = 1, FC27_DISPLAY_CHANGED = 2 };

static inline int fc27_native_display_apply(const char *build, uint64_t base,
                                           int width, int height,
                                           fc27_read_fn read_fn,
                                           fc27_write_fn write_fn, void *ctx) {
    if (!build || strcmp(build, "fb81983aa1cc3a2e97402497e2ca6528") ||
        width < 64 || height < 64 || width > 16384 || height > 16384 ||
        !base || !read_fn || !write_fn) return FC27_DISPLAY_REJECT;
    uint64_t owner = 0, settings = 0, type = 0, record = 0;
    if (!read_fn(ctx, base + 0xde7cd10, &owner, 8) || !owner ||
        !read_fn(ctx, owner + 0x23a8, &settings, 8) || !settings)
        return FC27_DISPLAY_PENDING;
    /* Constructor +0x9765670 stamps this exact TI at object+8; the singleton's
     * virtual getter +0x9764230 returns its +0x23a8 member. */
    if (!read_fn(ctx, settings + 8, &type, 8) || type != base + 0xda01b88 ||
        !read_fn(ctx, type, &record, 8) || record != base + 0xd1ff800)
        return FC27_DISPLAY_REJECT;
    uint32_t resize[8], startup[8];
    static const uint32_t resize_want[8] = {
        0xf951d669,0x39442928,0x7100051f,0x540000a1,
        0xb940a528,0xb9001fa8,0xb9409529,0x14000028 };
    static const uint32_t startup_want[8] = {
        0xf951d6a9,0x39442928,0x7100051f,0x540000a1,
        0xb940a528,0xb9001fa8,0xb9409529,0x14000028 };
    if (!read_fn(ctx, base + 0x9786568, resize, sizeof resize) ||
        !read_fn(ctx, base + 0x978675c, startup, sizeof startup) ||
        memcmp(resize, resize_want, sizeof resize) ||
        memcmp(startup, startup_want, sizeof startup)) return FC27_DISPLAY_REJECT;
    uint32_t old_width = 0, old_height = 0;
    uint8_t force = 0, single_heap = 0;
    if (!read_fn(ctx, settings + 0xa4, &old_width, 4) ||
        !read_fn(ctx, settings + 0x94, &old_height, 4) ||
        !read_fn(ctx, settings + 0x10a, &force, 1) ||
        !read_fn(ctx, settings + 0x128, &single_heap, 1))
        return FC27_DISPLAY_PENDING;
    if (force > 1 || single_heap > 1) return FC27_DISPLAY_REJECT;
    if (old_width == (uint32_t)width && old_height == (uint32_t)height &&
        force == 1 && single_heap == 0) return FC27_DISPLAY_UNCHANGED;
    /* Write dimensions first, then enable the existing engine branch. The
     * single-heap branch +0x9786820 replaces W/H with 1920x1080 even after a
     * forced size, so it must be off. Mark the engine's existing resize flag;
     * +0x9786500 checks it and calls ISwapChain::resize itself, on its thread. */
    uint32_t new_width = (uint32_t)width, new_height = (uint32_t)height;
    uint8_t zero = 0, one = 1;
    if (old_width != new_width) write_fn(ctx, settings + 0xa4, &new_width, 4);
    if (old_height != new_height) write_fn(ctx, settings + 0x94, &new_height, 4);
    if (single_heap) write_fn(ctx, settings + 0x128, &zero, 1);
    if (!force) write_fn(ctx, settings + 0x10a, &one, 1);
    write_fn(ctx, owner + 0x247c, &one, 1);
    return FC27_DISPLAY_CHANGED;
}
