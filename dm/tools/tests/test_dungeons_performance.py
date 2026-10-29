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
    MAIN_SOURCE = MAIN
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dm-dungeons-fps-')
        folder=Path(cls.tmp.name)
        source=(ROOT/'dm/host/hle_fpslock.c').read_text(encoding='utf8')
        source=source.replace('#include "hle.h"',PRELUDE,1).replace('#include <mach/mach.h>','',1)
        cfile=folder/'fps.c'; cfile.write_text(source+'\n'+cls.MAIN_SOURCE,encoding='utf8')
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

class ItTakesTwoFrameLimits(DungeonsFrameLimits):
    MAIN_SOURCE = (MAIN
        .replace('9e9d887d59f7f7db176b35e3379258b9', 'c4067e8cb3258656d8e9b448ee31aa38')
        .replace('0xae22510', '0xacf9130')
        .replace('0xac91a20', '0xab9ece8'))


UE_PRELUDE = r'''
#undef NDEBUG
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <stdatomic.h>
#include <stdbool.h>
#ifdef _WIN32
#include <windows.h>
static void test_pause(unsigned milliseconds) { Sleep(milliseconds); }
static void usleep(unsigned microseconds) { Sleep((microseconds+999)/1000); }
#else
#include <pthread.h>
#include <unistd.h>
static void test_pause(unsigned milliseconds) { usleep(milliseconds*1000); }
#endif
#define LOG(...) do { fprintf(stderr,__VA_ARGS__); fputc('\n',stderr); } while (0)
#define die(...) do { LOG(__VA_ARGS__); exit(86); } while (0)
#define TARGET_OS_IPHONE 1
typedef struct malloc_zone_s { unsigned version; const char *zone_name; void *(*malloc)(void *,size_t); } malloc_zone_t;
static malloc_zone_t custom_zone={16,"guest Unreal heap",NULL}, default_zone={16,"default",NULL};
static unsigned char old_block[128], probe_block[65536];
static int probe_frees, map_calls, unmaps, zone_renames;
static _Atomic int task_info_entered;
static int concurrent_case;
static malloc_zone_t *malloc_default_zone(void) { return &default_zone; }
static malloc_zone_t *malloc_create_zone(size_t n,unsigned flags) { (void)n;(void)flags;return &custom_zone; }
static const char *malloc_get_zone_name(malloc_zone_t *z) { return z->zone_name; }
static void malloc_set_zone_name(malloc_zone_t *z,const char *name) { assert(z!=&default_zone);z->zone_name=name;zone_renames++; }
static malloc_zone_t *malloc_zone_from_ptr(const void *p) { return p==old_block?&custom_zone:&default_zone; }
static size_t malloc_size(const void *p) { return p==old_block?sizeof old_block:4096; }
static size_t malloc_good_size(size_t n) { return (n+15)&~(size_t)15; }
static void *malloc_zone_malloc(malloc_zone_t *z,size_t n) {
    assert(n<=sizeof probe_block);
    if (z==&custom_zone) { errno=ENOMEM;return NULL; }
    return probe_block;
}
static void *malloc_zone_memalign(malloc_zone_t *z,size_t a,size_t n) { (void)a;return malloc_zone_malloc(z,n); }
static void *malloc_zone_realloc(malloc_zone_t *z,void *p,size_t n) { assert(z==&custom_zone&&p==old_block);(void)n;errno=ENOMEM;return NULL; }
static void malloc_zone_free(malloc_zone_t *z,void *p) { assert(z==&default_zone&&p==probe_block);probe_frees++; }
typedef uintptr_t vm_address_t;
typedef size_t vm_size_t;
typedef int kern_return_t, mach_msg_type_number_t;
typedef void *task_info_t;
typedef struct { uint64_t phys_footprint,limit_bytes_remaining; } task_vm_info_data_t;
#define TASK_VM_INFO_COUNT 2
#define TASK_VM_INFO 1
#define KERN_SUCCESS 0
#define VM_FLAGS_ANYWHERE 1
#define VM_MAKE_TAG(t) ((t)<<24)
#define VM_MEMORY_MALLOC_SMALL 2
#define MEMORY_OBJECT_NULL 0
#define FALSE 0
#define VM_PROT_READ 1
#define VM_PROT_WRITE 2
#define VM_INHERIT_DEFAULT 0
static int mach_task_self(void) { return 1; }
static int task_info(int t,int flavor,task_info_t p,mach_msg_type_number_t *n) {
    if (concurrent_case) { atomic_store(&task_info_entered,1);test_pause(80); }
    (void)t;(void)flavor;(void)n;task_vm_info_data_t *v=p;v->phys_footprint=1660ull<<20;v->limit_bytes_remaining=3400ull<<20;return 0;
}
static size_t os_proc_available_memory(void) { return (size_t)3400<<20; }
static kern_return_t vm_map(int task,vm_address_t *a,vm_size_t size,vm_address_t mask,int flags,int obj,size_t off,int copy,int prot,int maxprot,int inherit) {
    (void)task;(void)obj;(void)off;(void)copy;(void)prot;(void)maxprot;(void)inherit;
    assert(size==(4u<<20)&&mask==size-1);map_calls++;
    if (flags&VM_MAKE_TAG(VM_MEMORY_MALLOC_SMALL)) return 3;
    *a=0x80000000u;return 0;
}
static kern_return_t vm_deallocate(int task,vm_address_t a,vm_size_t size) { (void)task;assert(a==0x80000000u&&size==(4u<<20));unmaps++;return 0; }
typedef struct { const char *dli_sname; } Dl_info;
static int dladdr(void *p,Dl_info *d) { (void)p;d->dli_sname="test_zone_malloc";return 1; }
'''

UE_MAIN = r'''
#ifdef _WIN32
static DWORD WINAPI failing_thread(void *p) { (void)p;m_Malloc(NULL,4096,0);return 0; }
#else
static void *failing_thread(void *p) { (void)p;m_Malloc(NULL,4096,0);return NULL; }
#endif
int main(int argc,char **argv) {
    assert(argc==2);g_zone=&custom_zone;memset(old_block,0x5a,sizeof old_block);
    if (!strncmp(argv[1],"zone-",5)) {
        g_zone=ue_zone_create();
        if (!strcmp(argv[1],"zone-default")) assert(g_zone==&default_zone&&zone_renames==0);
        else assert(g_zone==&custom_zone&&zone_renames==1);
        return 0;
    }
    if (!strcmp(argv[1],"fatal")) { m_Malloc(NULL,4096,0);return 1; }
    if (!strcmp(argv[1],"concurrent")) {
        concurrent_case=1;
#ifdef _WIN32
        HANDLE first=CreateThread(NULL,0,failing_thread,NULL,0,NULL);assert(first);
#else
        pthread_t first;assert(!pthread_create(&first,NULL,failing_thread,NULL));
#endif
        while (!atomic_load(&task_info_entered)) test_pause(1);
        m_Malloc(NULL,4096,0);return 1;
    }
    if (!strcmp(argv[1],"realloc")) {
        assert(m_TryRealloc(NULL,old_block,4096,0)==NULL);
        assert(old_block[0]==0x5a&&old_block[127]==0x5a);
    } else {
        assert(m_TryMalloc(NULL,4096,0)==NULL);
        assert(m_TryMalloc(NULL,4096,0)==NULL);
    }
    assert(errno==ENOMEM);
    assert(probe_frees==1&&map_calls==2&&unmaps==1);
    return 0;
}
'''


class UnrealAllocatorFailureDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dm-ue-allocator-')
        whole=(ROOT/'dm/host/hle_uemalloc.c').read_text(encoding='utf-8')
        source=whole[whole.index('static malloc_zone_t *g_zone;'):whole.index('static void *g_vt[NSLOT];')]
        if 'static malloc_zone_t *ue_zone_create(' not in source:
            # Execute the existing production initialization before that operation
            # is factored into a helper, so the selector regression fails at run time.
            start=whole.index('g_zone = malloc_create_zone(')
            legacy=whole[start:whole.index('g_what = k_ue[k].what;',start)]
            source+='\nstatic malloc_zone_t *ue_zone_create(void) { '+legacy+' return g_zone; }\n'
        folder=Path(cls.tmp.name);cfile=folder/'allocator.c';cls.exe=folder/('allocator.exe' if os.name=='nt' else 'allocator')
        cfile.write_text(UE_PRELUDE+'\n'+source+'\n'+UE_MAIN,encoding='utf-8')
        cc=[p.strip('"') for p in shlex.split(os.environ.get('CC','cc'),posix=os.name!='nt')]
        built=subprocess.run(cc+['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable',str(cfile),'-o',str(cls.exe)],capture_output=True,text=True)
        if built.returncode:raise AssertionError(built.stdout+built.stderr)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_failed_try_malloc_reports_once_and_releases_native_probes(self):
        result=subprocess.run([str(self.exe),'malloc'],capture_output=True,text=True)
        self.assertIn('UE malloc failure',result.stderr)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stderr.count('UE malloc failure'),1)
    def test_failed_realloc_preserves_pointer_contents_and_original_errno(self):
        result=subprocess.run([str(self.exe),'realloc'],capture_output=True,text=True)
        self.assertIn('UE malloc failure',result.stderr)
        self.assertIn('owner=',result.stderr)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_fatal_allocation_still_terminates_after_diagnostics(self):
        result=subprocess.run([str(self.exe),'fatal'],capture_output=True,text=True)
        self.assertIn('UE malloc failure',result.stderr)
        self.assertEqual(result.returncode,86,result.stderr)
    def test_explicit_default_zone_does_not_rename_the_process_default(self):
        result=subprocess.run([str(self.exe),'zone-default'],env=dict(os.environ,DM_UE_ALLOCATOR='default'),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_custom_zone_remains_the_baseline(self):
        result=subprocess.run([str(self.exe),'zone-custom'],env=dict(os.environ,DM_UE_ALLOCATOR='custom'),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_concurrent_fatal_waits_for_the_first_probe_report(self):
        result=subprocess.run([str(self.exe),'concurrent'],capture_output=True,text=True,timeout=5)
        self.assertIn('UE allocation probes',result.stderr)
        self.assertEqual(result.returncode,86,result.stderr)


if __name__=='__main__': unittest.main()
