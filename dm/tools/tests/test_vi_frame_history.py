"""Exercise the actual VI entry point and the portable presentation history."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class FrameHistory(unittest.TestCase):
    def run_c(self, source):
        compiler = [s.strip('"') for s in shlex.split(os.environ.get('CC', 'cc'), posix=os.name != 'nt')]
        with tempfile.TemporaryDirectory(prefix='vi-history-') as folder:
            path = Path(folder)
            src, exe = path / 'check.c', path / ('check.exe' if os.name == 'nt' else 'check')
            src.write_text(source, encoding='utf-8')
            build = subprocess.run(compiler + ['-std=c11', '-Wall', '-Wextra', '-Werror',
                                   '-I', str(ROOT / 'dm/gfx'), str(src), '-o', str(exe)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_vi_entry_point_returns_renderer_history(self):
        text = (ROOT / 'dm/gfx/hle_vi.c').read_text(encoding='utf-8')
        start = text.index('HLE_FORCE("_ZN2nn2vi16ListFrameHistory')
        end = text.index('\n}', start) + 2
        self.run_c(r'''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define LOG(...) do { if (0) printf(__VA_ARGS__); } while (0)
#define HLE_FORCE(symbol, why, result, name, ...) result name(__VA_ARGS__)
static int calls;
int dm_nvn_frame_history(void *out, int n) {
    calls++;
    if (!out || !n) return 8;
    if (n < 0) return 0;
    uint64_t *p = out;
    p[0] = 2; p[1] = 2; p[2] = 100; p[3] = p[4] = 200;
    return 1;
}
''' + text[start:end] + r'''
int main(void) {
    uint64_t record[5] = {0};
    assert(h_vi_FrameHist(0, 0, 0) == 8);
    assert(h_vi_FrameHist(record, 1, 0) == 1);
    assert(calls == 2 && record[0] == 2 && record[1] == 2);
    return 0;
}
''')

    def test_only_presented_frames_are_complete_and_history_is_bounded(self):
        self.run_c(r'''
#include <assert.h>
#include <stddef.h>
#include "vi_frame_history.h"
static int64_t displayed_tick = 19200000;
static int64_t completed(uint64_t ticket) {
    if (ticket == 102) return displayed_tick;
    if (ticket == 103) return -1;
    return 0;
}
int main(void) {
    dm_vi_history h = {0};
    dm_vi_frame_info out[9] = {{0}};
    assert(sizeof(dm_vi_frame_info) == 0x28);
    assert(offsetof(dm_vi_frame_info, presented) == 0x18);
    assert(dm_vi_history_list(&h, 0, 0, completed) == 8);
    assert(dm_vi_history_list(&h, out, -1, completed) == 0);
    assert(dm_vi_history_list(&h, out, 8, completed) == 0);
    dm_vi_history_push(&h, 1, 101, 10, 10);
    dm_vi_history_push(&h, 2, 102, 20, 20);
    dm_vi_history_push(&h, 3, 103, 30, 30);
    assert(dm_vi_history_list(&h, out, 8, completed) == 3);
    assert(out[0].frame == 3 && out[0].type == 1 && !out[0].presented);
    assert(out[1].type == 2 && out[1].frame == 2 && out[1].queued == 20);
    assert(out[1].presented == 19200000 && out[1].displayed == 19200000);
    assert(out[2].frame == 1 && out[2].type == 1 && !out[2].presented);
    displayed_tick = 9600000; // A changed guest clock cannot change past timestamps.
    assert(dm_vi_history_list(&h, out, 8, completed) == 3 && out[1].presented == 19200000);
    assert(dm_vi_history_list(&h, out, 1, completed) == 1 && out[0].frame == 3);
    for (uint64_t i = 4; i <= 20; ++i) dm_vi_history_push(&h, i, i + 100, i * 10, i * 10);
    out[8].frame = 0x1234;
    assert(dm_vi_history_list(&h, out, 99, completed) == 8);
    assert(out[0].frame == 20 && out[7].frame == 13 && out[8].frame == 0x1234);
    dm_vi_history anchored = {0};
    dm_vi_history_push(&anchored, 1, 102, 100, 200);
    displayed_tick = 201; // First query may occur after the guest clock was frozen.
    assert(dm_vi_history_list(&anchored, out, 8, completed) == 1 && out[0].presented == 101);
    return 0;
}
''')


if __name__ == '__main__':
    unittest.main()
