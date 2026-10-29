"""Execute the production frame-limit code with the measured Dungeons build.

Only Mach memory reads and host declarations are replaced for portability.
Each executable invocation gets fresh production initialization state.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PRELUDE = r'''
#undef NDEBUG
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <math.h>
#define LOG(...) do { if (0) printf(__VA_ARGS__); } while (0)
#define DM_GAME_FPS_TARGET 0
typedef struct { char name[16], build_id[65]; uint8_t *base; } module_t;
static module_t modules[1], *g_mod = modules;
static int g_nmod = 1, writes;
static uint8_t *allocation;
static float fps[2];
static int32_t syncs[2];
typedef size_t vm_size_t;
typedef uintptr_t vm_address_t;
#define KERN_SUCCESS 0
static int mach_task_self(void) { return 0; }
static int vm_read_overwrite(int task, uintptr_t a, size_t n, uintptr_t out, size_t *got) {
    (void)task;
    if (!((a >= (uintptr_t)allocation && a+n <= (uintptr_t)allocation+0xb000000) ||
          (a >= (uintptr_t)fps && a+n <= (uintptr_t)(fps+2)) ||
          (a >= (uintptr_t)syncs && a+n <= (uintptr_t)(syncs+2)))) return 1;
    memcpy((void *)out, (void *)a, n); *got=n; return KERN_SUCCESS;
}
static void dm_guest_write_prepare(void *p, size_t n) {
    assert(n==4);
    assert(p==fps || p==fps+1 || p==syncs || p==syncs+1);
    writes++;
}
'''
MAIN = r'''
int main(int argc, char **argv) {
    assert(argc==2);
    allocation=calloc(1,0xb000000); assert(allocation);
    strcpy(g_mod[0].name,"main"); g_mod[0].base=allocation;
    strcpy(g_mod[0].build_id,"9e9d887d59f7f7db176b35e3379258b9");
    *(uintptr_t *)(allocation+0xae22510)=(uintptr_t)fps;
    *(uintptr_t *)(allocation+0xac91a20)=(uintptr_t)syncs;
    fps[0]=fps[1]=30; syncs[0]=syncs[1]=2;
    if (!strcmp(argv[1],"unknown")) g_mod[0].build_id[31]='0';
    if (!strcmp(argv[1],"late")) {
        *(uintptr_t *)(allocation+0xae22510)=0;
        *(uintptr_t *)(allocation+0xac91a20)=0;
        dm_fps_lock_tick(); assert(writes==0);
        *(uintptr_t *)(allocation+0xae22510)=(uintptr_t)fps;
        *(uintptr_t *)(allocation+0xac91a20)=(uintptr_t)syncs;
    }
    if (!strcmp(argv[1],"zero")) fps[0]=fps[1]=0;
    if (!strcmp(argv[1],"nan")) fps[0]=fps[1]=NAN;
    if (!strcmp(argv[1],"30")) { fps[0]=fps[1]=60; syncs[0]=syncs[1]=1; }
    dm_fps_lock_tick();
    if (!strcmp(argv[1],"unknown") || !strcmp(argv[1],"off") || !strcmp(argv[1],"invalid")) {
        assert(writes==0 && fps[0]==30 && fps[1]==30 && syncs[0]==2 && syncs[1]==2);
    } else if (!strcmp(argv[1],"zero") || !strcmp(argv[1],"nan")) {
        assert(writes==2 && syncs[0]==1 && syncs[1]==1);
        assert(!strcmp(argv[1],"nan") ? isnan(fps[0]) && isnan(fps[1]) : fps[0]==0 && fps[1]==0);
    } else {
        int target=!strcmp(argv[1],"30")?30:60;
        assert(fps[0]==target && fps[1]==target && syncs[0]==60/target && syncs[1]==60/target && writes==4);
        dm_fps_lock_tick(); assert(writes==4);
        fps[0]=fps[1]=30; syncs[0]=syncs[1]=2;
        dm_fps_lock_tick();
        assert(fps[0]==target && fps[1]==target && syncs[0]==60/target && syncs[1]==60/target);
    }
    free(allocation); return 0;
}
'''

class DungeonsFrameLimits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dm-dungeons-fps-')
        folder=Path(cls.tmp.name)
        source=(ROOT/'dm/host/hle_fpslock.c').read_text(encoding='utf8')
        source=source.replace('#include "hle.h"',PRELUDE,1).replace('#include <mach/mach.h>','',1)
        cfile=folder/'fps.c'; cfile.write_text(source+'\n'+MAIN,encoding='utf8')
        cls.exe=folder/('fps.exe' if os.name=='nt' else 'fps')
        cc=[p.strip('"') for p in shlex.split(os.environ.get('CC','cc'),posix=os.name!='nt')]
        built=subprocess.run(cc+['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function',str(cfile),'-o',str(cls.exe)],capture_output=True,text=True)
        if built.returncode: raise AssertionError(built.stdout+built.stderr)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def case(self,name,target='60'):
        env=dict(os.environ,DM_FPS_TARGET=target)
        run=subprocess.run([str(self.exe),name],env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
    def test_both_engine_limits_follow_60_and_survive_config_reset(self): self.case('60')
    def test_explicit_30_target_updates_both_copies(self): self.case('30','30')
    def test_late_console_variable_initialization_is_retried(self): self.case('late')
    def test_unregistered_build_is_untouched(self): self.case('unknown')
    def test_zero_target_leaves_original_game_limits(self): self.case('off','0')
    def test_invalid_target_is_untouched(self): self.case('invalid','120')
    def test_unlimited_float_value_is_preserved(self): self.case('zero')
    def test_uninitialized_nan_is_not_written(self): self.case('nan')

if __name__=='__main__': unittest.main()
