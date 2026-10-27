// The host learns a shader's output types from the pipeline Metal refused. See dm_shader_learn.h for what and why.
#import <Foundation/Foundation.h>
#include "dm_shader_learn.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <os/lock.h>

// ---- the rows ----------------------------------------------------------------------------------------------------
// One row per shader: the colour slots it must declare as unsigned (bits 0-7) and signed (bits 8-15). A few thousand of
// them at most -- every shader a game ever draws with a mismatch -- so a linear lookup is enough and keeps this file
// free of the shell's hash maps.
enum { LEARN_ROWS = 8192, LEARN_KEY = 32 };
static struct { char key[LEARN_KEY]; unsigned mask; } g_rows[LEARN_ROWS];
static int g_nrows, g_loaded;
static os_unfair_lock g_lock = OS_UNFAIR_LOCK_INIT;

int dm_shader_learn_enabled(void) {
    static int v = -1;
    if (v < 0) { const char *e = getenv("DM_SHADER_LEARN"); v = !(e && !strcmp(e, "0")); }
    return v;
}

// Documents/dm_shader_learn.tsv. DM_SAVE is the file the shell hands the game for its own documents (pso_user.tsv sits
// beside it), so what a game teaches the shell lands with everything else it learns; a build without it uses Documents.
static char g_path[PATH_MAX];
static const char *learn_path(void) {
    static int once;
    if (!once) {
        once = 1;
        const char *s = getenv("DM_SAVE");
        if (s && *s) { snprintf(g_path, sizeof g_path, "%s", s); char *slash = strrchr(g_path, '/'); if (slash) *slash = 0; }
        else { NSString *d = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
               if (d) snprintf(g_path, sizeof g_path, "%s", d.UTF8String); }
        size_t n = strlen(g_path);
        if (n && n + 24 < sizeof g_path) snprintf(g_path + n, sizeof g_path - n, "/dm_shader_learn.tsv");
        else g_path[0] = 0;
    }
    return g_path[0] ? g_path : NULL;
}

const char *dm_shader_learn_path(void) { return learn_path(); }

static int row_find(const char *key) {   // caller holds g_lock
    for (int i = 0; i < g_nrows; i++) if (!strcmp(g_rows[i].key, key)) return i;
    return -1;
}

static void learn_load(void) {   // caller holds g_lock
    if (g_loaded) return;
    g_loaded = 1;
    const char *p = learn_path();
    FILE *f = p ? fopen(p, "r") : NULL;
    if (!f) return;
    char line[512];
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#') continue;
        char key[LEARN_KEY]; unsigned um = 0, sm = 0;
        if (sscanf(line, "%31s %u %u", key, &um, &sm) < 3) continue;
        if (g_nrows >= LEARN_ROWS) break;
        snprintf(g_rows[g_nrows].key, LEARN_KEY, "%s", key);
        g_rows[g_nrows].mask = (um & 0xff) | ((sm & 0xff) << 8);
        g_nrows++;
    }
    fclose(f);
}

unsigned dm_shader_learn_mask(const char *key) {
    if (!key || !*key) return 0;
    os_unfair_lock_lock(&g_lock);
    learn_load();
    int i = row_find(key);
    unsigned m = i >= 0 ? g_rows[i].mask : 0;
    os_unfair_lock_unlock(&g_lock);
    return m;
}

void dm_shader_learn_note(const char *key, unsigned mask, const char *why) {
    if (!key || !*key || !mask) return;
    os_unfair_lock_lock(&g_lock);
    learn_load();
    int i = row_find(key);
    unsigned old = i >= 0 ? g_rows[i].mask : 0;
    if ((old | mask) == old) { os_unfair_lock_unlock(&g_lock); return; }   // learned already (a second pipeline of the same pass)
    if (i < 0) { if (g_nrows >= LEARN_ROWS) { os_unfair_lock_unlock(&g_lock); return; } i = g_nrows++; snprintf(g_rows[i].key, LEARN_KEY, "%s", key); }
    g_rows[i].mask = old | mask;
    const char *p = learn_path();
    int fresh = p && access(p, F_OK) != 0;
    FILE *f = p ? fopen(p, fresh ? "w" : "a") : NULL;
    if (f) {
        if (fresh)
            fprintf(f, "# Shaders whose colour output type the host learned from a refused render pipeline.\n"
                       "# key\tunsigned slots\t signed slots\twhat the pass bound\n"
                       "# Written by the shell (dm_shader_learn.m). dm_shader_prep reads it, so a shader that was ever\n"
                       "# refused is compiled with the right output types the next time the shaders are prepared.\n"
                       "# Delete this file to forget everything; a shader is then learned again when it is first drawn.\n");
        fprintf(f, "%s\t%u\t%u\t%s\n", key, (old | mask) & 0xff, ((old | mask) >> 8) & 0xff, why && *why ? why : "");
        fflush(f);
        fclose(f);
    }
    os_unfair_lock_unlock(&g_lock);
}

// ---- the rewrite -------------------------------------------------------------------------------------------------
// The source is the translator's spirv-cross output, and its shape is fixed:
//
//     struct main0_out
//     {
//         float4 m_48 [[color(0)]];
//         float4 m_58 [[color(5)]];
//     };
//     fragment main0_out main0(main0_in in [[stage_in]], ...)
//     {
//         main0_out out = {};
//         out.m_58.x = (*spvDescriptorSet0.fp_c3)._m0[1].x;
//         return out;
//     }
//
// so a slot becomes integer by changing one declaration and converting the values written to it -- exactly what the
// translator emits when a shader_facts_manual.tsv row names the slot (uint4 m_70; out.m_70.x = uint(_580);), the shape
// 161 device-verified Kirby shaders already have. The conversion is the value conversion the console's hardware does,
// not a bit reinterpretation: the row that fixes these shaders' picture is the one that converts the value.

typedef struct {
    char name[40];
    char to[8];       // the new type, e.g. "uint4"
    char scalar[5];   // the conversion of one component, e.g. "uint"
    size_t t0, t1;    // where the declaration's type token sits in the source
} lfield;

static int ident(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_'; }

// The output declarations this mask asks to change. Returns how many, 0 when the source declares none of those slots as
// float (nothing to do -- it was already fixed, by a facts row or an earlier launch), or -1 when one of them is a type
// this rewrite has no conversion for.
static int learn_collect(const char *src, size_t len, unsigned mask, lfield *f, int max) {
    int n = 0;
    const char *end = src + len;
    for (const char *q = src; (q = strnstr(q, "[[color(", (size_t)(end - q))); q++) {
        const char *d = q + 8;
        unsigned slot = 0;
        int digits = 0;
        while (d < end && *d >= '0' && *d <= '9' && digits < 3) { slot = slot * 10 + (unsigned)(*d++ - '0'); digits++; }
        if (!digits || d + 4 > end || memcmp(d, ")]]", 3) || d[3] != ';' || slot > 7) continue;
        // the whole line: <ws><type><ws><name><ws>[[color(N)]];
        const char *s = q;
        while (s > src && s[-1] != '\n') s--;
        const char *p = s;
        while (p < q && (*p == ' ' || *p == '\t')) p++;
        const char *t0 = p;
        while (p < q && ident(*p)) p++;
        const char *t1 = p;
        if (t1 == t0 || t1 - t0 > 6) continue;
        while (p < q && (*p == ' ' || *p == '\t')) p++;
        const char *n0 = p;
        while (p < q && ident(*p)) p++;
        const char *n1 = p;
        if (n1 == n0 || n1 - n0 >= 40) continue;
        while (p < q && (*p == ' ' || *p == '\t')) p++;
        if (p != q) continue;
        int want = (mask >> slot) & 1 ? 1 : (mask >> (8 + slot)) & 1 ? 2 : 0;
        if (!want) continue;
        char type[8]; size_t tl = (size_t)(t1 - t0); memcpy(type, t0, tl); type[tl] = 0;
        int ncomp = 1;
        if (tl > 1 && type[tl - 1] >= '2' && type[tl - 1] <= '4') ncomp = type[tl - 1] - '0';
        size_t base = tl > 1 && type[tl - 1] >= '2' && type[tl - 1] <= '4' ? tl - 1 : tl;
        int is_float = (base == 5 && !strncmp(type, "float", 5)) || (base == 4 && !strncmp(type, "half", 4));
        if (!is_float) {
            if (want == 1 && !strncmp(type, "uint", 4)) continue;   // already unsigned: nothing to rewrite for it
            if (want == 2 && !strncmp(type, "int", 3)) continue;
            return -1;
        }
        if (n >= max) return -1;
        snprintf(f[n].name, sizeof f[n].name, "%.*s", (int)(n1 - n0), n0);
        if (ncomp > 1) snprintf(f[n].to, sizeof f[n].to, "%s%d", want == 2 ? "int" : "uint", ncomp);
        else snprintf(f[n].to, sizeof f[n].to, "%s", want == 2 ? "int" : "uint");
        snprintf(f[n].scalar, sizeof f[n].scalar, "%s", want == 2 ? "int" : "uint");
        f[n].t0 = (size_t)(t0 - src);
        f[n].t1 = (size_t)(t1 - src);
        n++;
    }
    return n;
}

typedef struct { char *p; size_t n, cap; int oom; } obuf;
static void oput(obuf *b, const char *s, size_t n) {
    if (b->oom || !n) return;
    if (b->n + n + 1 > b->cap) {
        size_t c = b->cap ? b->cap : 8192;
        while (c < b->n + n + 1) c += c / 2;
        char *q = realloc(b->p, c);
        if (!q) { b->oom = 1; return; }
        b->p = q; b->cap = c;
    }
    memcpy(b->p + b->n, s, n); b->n += n; b->p[b->n] = 0;
}

char *dm_shader_learn_rewrite(const char *src, size_t len, unsigned mask, size_t *out_len) {
    if (!src || !len || !mask) return NULL;
    lfield f[8];
    int nf = learn_collect(src, len, mask, f, 8);
    if (nf <= 0) return NULL;
    obuf b = {0};
    oput(&b, "", 0);   // takes the first allocation before anything is copied into it
    size_t i = 0;
    while (i < len && !b.oom) {
        int hit = -1;
        for (int k = 0; k < nf; k++) if (i == f[k].t0) { hit = k; break; }
        if (hit >= 0) {   // the declaration's type: written at the same length, so nothing after it moves
            size_t tl = f[hit].t1 - f[hit].t0, nl = strlen(f[hit].to);
            if (nl > tl) break;   // unreachable: float4 -> uint4 is shorter
            oput(&b, f[hit].to, nl);
            for (size_t z = nl; z < tl; z++) oput(&b, " ", 1);
            i = f[hit].t1;
            continue;
        }
        if (src[i] == '.') {
            int k = -1;
            for (int j = 0; j < nf && k < 0; j++) {
                size_t nl = strlen(f[j].name);
                if (i + 1 + nl <= len && !memcmp(src + i + 1, f[j].name, nl) && (i + 1 + nl == len || !ident(src[i + 1 + nl]))) k = j;
            }
            if (k >= 0) {
                size_t j = i + 1 + strlen(f[k].name);
                int whole = 1;
                if (j + 1 < len && src[j] == '.' && src[j + 1] && strchr("xyzw", src[j + 1])) { j += 2; whole = 0; }
                size_t lhs_end = j;
                while (j < len && (src[j] == ' ' || src[j] == '\t')) j++;
                if (j >= len || src[j] != '=' || (j + 1 < len && src[j + 1] == '=')) break;   // used as a value: not guessed at
                size_t eq = j, e = j + 1;
                int depth = 0;
                for (; e < len; e++) {
                    char c = src[e];
                    if (c == '(' || c == '[' || c == '{') depth++;
                    else if (c == ')' || c == ']' || c == '}') { if (--depth < 0) break; }
                    else if (c == ';' && depth == 0) break;
                }
                if (e >= len) break;
                const char *conv = whole ? f[k].to : f[k].scalar;
                oput(&b, src + i, lhs_end - i);             // ".m_58" or ".m_58.x"
                oput(&b, src + lhs_end, eq + 1 - lhs_end);   // the spaces and "="
                oput(&b, " ", 1);
                oput(&b, conv, strlen(conv)); oput(&b, "(", 1);
                oput(&b, src + eq + 1, e - eq - 1);          // the value
                oput(&b, ")", 1);
                i = e;
                continue;
            }
        }
        oput(&b, src + i, 1);
        i++;
    }
    if (b.oom || i < len) { free(b.p); return NULL; }   // gave up part-way: hand back nothing rather than half a shader
    if (out_len) *out_len = b.n;
    return b.p;
}
