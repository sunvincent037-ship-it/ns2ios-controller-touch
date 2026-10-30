"""Execute the shared aspect policy and the real exact-build observation handler."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HOST = ROOT / 'dm/host'


class DisplayAspect(unittest.TestCase):
    def compile_and_run(self, source, cases):
        compiler = [part.strip('"') for part in shlex.split(os.environ.get('CC', 'cc'), posix=os.name != 'nt')]
        self.assertTrue(shutil.which(compiler[0]), 'set CC to a portable C compiler')
        with tempfile.TemporaryDirectory(prefix='dm-display-aspect-') as directory:
            folder = Path(directory)
            cfile, exe = folder/'test.c', folder/('test.exe' if os.name == 'nt' else 'test')
            cfile.write_text(source, encoding='utf-8')
            built = subprocess.run(compiler+['-std=c11','-Wall','-Wextra','-Werror','-I',str(HOST),str(cfile),'-o',str(exe)], capture_output=True,text=True)
            self.assertEqual(built.returncode, 0, built.stdout+built.stderr)
            for case, aspect in cases:
                env = dict(os.environ)
                env.pop('DM_DISPLAY_ASPECT', None)
                if aspect is not None:
                    env['DM_DISPLAY_ASPECT'] = aspect
                result = subprocess.run([str(exe),case], env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,f'{case}: '+result.stdout+result.stderr)

    def test_bounded_geometry_preserves_uniform_scale_and_defaults(self):
        self.assertTrue((HOST/'display_aspect.h').is_file(), 'Shared display aspect policy is missing')
        self.compile_and_run(r'''
#include <assert.h>
#include <math.h>
#include "display_aspect.h"
int main(int argc, char **argv) {
    (void)argc; (void)argv;
    assert(dm_display_aspect(0)==0);
    assert(dm_display_aspect("")==0);
    assert(dm_display_aspect("16:9")>1.777 && dm_display_aspect("16:9")<1.778);
    const char *bad[]={"0:9","16:0","-16:9","16:9junk","16/9","nan:9","1:4","99:1","999999999999999999999:9","16 :9","16: 9"};
    for (unsigned i=0;i<sizeof bad/sizeof *bad;i++) assert(dm_display_aspect(bad[i])==0);
    double a=dm_display_aspect("1210:834");
    assert(a>1.450 && a<1.451);
    assert(dm_display_height(1920,1080,a)==1323);
    assert(dm_display_height(1280,720,a)==882);
    assert(dm_display_height(1920,1080,0)==1080);
    assert(dm_display_height(1920,1323,a)==1323);
    assert(dm_display_height(0,1080,a)==1080);
    assert(dm_display_height(16384,1080,a)==1080);
    assert(dm_display_height(1920,1080,NAN)==1080);
    double w=1210,h=834;
    dm_display_fit(&w,&h,a);
    assert(fabs(w-1210)<0.001 && fabs(h-834)<0.001);
    w=1210; h=834; dm_display_fit(&w,&h,0);
    assert(fabs(w-1210)<0.001 && fabs(h-680.625)<0.001);
    w=2500; h=1000; dm_display_fit(&w,&h,a);
    assert(w<=2500 && h<=1000 && fabs(w/h-a)<0.000001);
    return 0;
}
''', [('geometry', None)])

    def test_observation_is_exact_build_gated_and_only_changes_height_operand(self):
        path = HOST/'hle_display.c'
        self.assertTrue(path.is_file(), 'Resolution observation is missing')
        actual = '\n'.join(line for line in path.read_text().splitlines() if line != '#include "hle.h"')
        source = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define LOG(...) ((void)0)
enum { OBS_VIEWPORT_SIZE=26 };
static struct { char name[16],build_id[40]; } g_mod[1];
static int g_nmod=1, present=1, registrations;
static void (*handler)(uint64_t *,int);
static int gate_obs_present(int id) { assert(id==26); return present; }
static void gate_obs_set(int id,void (*fn)(uint64_t *,int)) { assert(id==26); handler=fn; registrations++; }
'''+actual+r'''
int main(int argc,char **argv) {
    assert(argc==2);
    strcpy(g_mod[0].name,"main");
    strcpy(g_mod[0].build_id,"c4067e8cb3258656d8e9b448ee31aa38");
    if (!strcmp(argv[1],"unknown")) g_mod[0].build_id[0]='0';
    if (!strcmp(argv[1],"no_gate")) present=0;
    dm_display_install();
    if (strcmp(argv[1],"enabled")) { assert(!registrations && !handler); return 0; }
    assert(registrations==1 && handler);
    uint64_t regs[31],old[31];
    for(int i=0;i<31;i++) regs[i]=(uint64_t)i+900;
    regs[19]=1080; regs[20]=1920; memcpy(old,regs,sizeof regs);
    handler(regs,0); assert(regs[19]==1323);
    for(int i=0;i<31;i++) if(i!=19) assert(regs[i]==old[i]);
    regs[19]=720; regs[20]=1280; handler(regs,0); assert(regs[19]==882);
    regs[19]=1323; regs[20]=1920; handler(regs,0); assert(regs[19]==1323);
    return 0;
}
'''
        self.compile_and_run(source, [('enabled','1210:834'),('unknown','1210:834'),('no_gate','1210:834'),('disabled',None),('invalid','16:0')])


if __name__ == '__main__':
    unittest.main()
