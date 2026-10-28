// Stable local identities shared by account selection and per-user save mounts.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

enum { DM_LOCAL_USER_MAX = 8 };
typedef struct { uint64_t v[2]; } dm_local_uid;

static inline int dm_local_user_count(void) {
    const char *s = getenv("DM_LOCAL_USERS");
    return s && s[0] >= '1' && s[0] <= '8' && !s[1] ? s[0] - '0' : 1;
}

static inline dm_local_uid dm_local_user_uid(int index) {
    dm_local_uid uid = {{0x78626c0000000001ull + (uint64_t)index, 0x53574e4154495645ull}};
    return uid;
}

static inline int dm_local_user_index(const void *value) {
    if (!value) return -1;
    dm_local_uid uid; memcpy(&uid, value, sizeof uid);
    dm_local_uid primary = dm_local_user_uid(0);
    uint64_t index = uid.v[0] - primary.v[0];
    return uid.v[1] == primary.v[1] && index < (uint64_t)dm_local_user_count() ? (int)index : -1;
}

// Secondary backing directories are siblings of the primary, each with its own .work / .new transaction.
// Reserve .work plus its terminator in the mount's path buffer, so mount_ex cannot silently truncate it.
static inline int dm_local_user_save_path(char *out, size_t cap, const char *base, const void *uid) {
    if (!out || !cap) return 0;
    out[0] = 0;
    if (!base || !*base) return 0;
    int index = uid && dm_local_user_count() > 1 ? dm_local_user_index(uid) : 0;
    if (index < 0) return 0;
    size_t n = strlen(base);
    while (n > 1 && base[n - 1] == '/') n--;
    size_t suffix = index ? 6 : 0;   // _user2 through _user8
    if (index && n == 1 && base[0] == '/') return 0;   // the filesystem root has no sibling
    if (cap < sizeof ".work" || n > cap - sizeof ".work" || suffix > cap - sizeof ".work" - n) return 0;
    memcpy(out, base, n);
    if (index) { memcpy(out + n, "_user", 5); out[n + 5] = (char)('1' + index); }
    out[n + suffix] = 0;
    return 1;
}
