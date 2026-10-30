// Exact-build adaptation of the game's existing resolution request, before its
// native formatter and resize callbacks run. No console strings are rewritten.
#include "hle.h"
#include "display_aspect.h"

static double g_display_aspect;

static void viewport_size(uint64_t *regs, int param) {
    (void)param;
    // At main+0x5477f34 in the measured build: w20 is width, w19 is height;
    // the original mov w2,w19 runs after this observation and passes the height
    // into the existing r.SetRes formatter. Later settings resets take it too.
    int width = (int)(uint32_t)regs[20], old_height = (int)(uint32_t)regs[19];
    int height = dm_display_height(width, old_height, g_display_aspect);
    if (height != old_height) {
        regs[19] = (uint32_t)height;
        LOG("display aspect: native viewport request %dx%d -> %dx%d", width, old_height, width, height);
    }
}

void dm_display_install(void) {
    g_display_aspect = dm_display_aspect(getenv("DM_DISPLAY_ASPECT"));
    if (!g_display_aspect) return;
    for (int i = 0; i < g_nmod; i++)
        if (!strcmp(g_mod[i].name, "main") &&
            !strcmp(g_mod[i].build_id, "c4067e8cb3258656d8e9b448ee31aa38")) {
            if (!gate_obs_present(OBS_VIEWPORT_SIZE)) {
                LOG("[RED] display aspect: this Guest lacks the measured viewport observation; native sizing is not enabled");
                return;
            }
            gate_obs_set(OBS_VIEWPORT_SIZE, viewport_size);
            return;
        }
}
