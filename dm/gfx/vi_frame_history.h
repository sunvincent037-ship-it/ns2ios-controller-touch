#pragma once
#include <stdint.h>

// SDK FrameInfo ABI: status, frame number, queue tick, and two display ticks.
// The SDK's count-only query reports space for eight records.
enum { DM_VI_HISTORY_CAPACITY = 8 };
typedef struct {
    uint64_t type, frame;
    int64_t queued, presented, displayed;
} dm_vi_frame_info;
typedef struct { uint64_t frame, ticket; int64_t queued, completion, clock_offset; } dm_vi_frame_record;
typedef struct {
    dm_vi_frame_record records[DM_VI_HISTORY_CAPACITY];
    uint64_t count;
} dm_vi_history;

static inline int64_t dm_vi_ns_ticks(uint64_t ns) {
    return (int64_t)((ns / 1000000000ull) * 19200000ull
                   + (ns % 1000000000ull) * 192ull / 10000ull);
}
// The caller serializes pushes and queries. Cache each completed tick once:
// changing the deterministic guest clock later must not rewrite old history.
static inline void dm_vi_history_push(dm_vi_history *h, uint64_t frame,
                                     uint64_t ticket, int64_t queued, int64_t host_tick) {
    h->records[h->count++ % DM_VI_HISTORY_CAPACITY] = (dm_vi_frame_record){frame, ticket, queued, 0, queued - host_tick};
}
static inline int dm_vi_history_list(dm_vi_history *h, dm_vi_frame_info *out,
                                    int n, int64_t (*completed)(uint64_t)) {
    if (!out || n == 0) return DM_VI_HISTORY_CAPACITY;
    if (n < 0) return 0;
    int count = h->count < DM_VI_HISTORY_CAPACITY ? (int)h->count : DM_VI_HISTORY_CAPACITY;
    if (count > n) count = n;
    for (int i = 0; i < count; ++i) {
        // SDK ListFrameHistory sorts by descending frame number. A client may
        // use only the first completed entry, including while a fence blocks.
        dm_vi_frame_record *r = &h->records[(h->count - 1 - (uint64_t)i) % DM_VI_HISTORY_CAPACITY];
        if (!r->completion) {
            int64_t tick = completed(r->ticket);
            // The queue-time anchor also covers a first query after a clock
            // freeze; a later guest/host offset cannot rewrite this frame.
            r->completion = tick > 0 ? tick + r->clock_offset : tick;
        }
        int64_t tick = r->completion;
        out[i] = (dm_vi_frame_info){tick > 0 ? 2 : 1, r->frame, r->queued,
                                   tick > 0 ? tick : 0, tick > 0 ? tick : 0};
    }
    return count;
}
