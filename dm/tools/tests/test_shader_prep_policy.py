"""Portable execution tests for optional shader precompilation admission."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
IOS = ROOT / 'dm/ios/Sources'


class ShaderPrepPolicy(unittest.TestCase):
    def test_admission_and_thermal_budget(self):
        header = IOS / 'dm_shader_prep_policy.h'
        self.assertTrue(header.is_file(), 'shader preparation needs a bounded admission policy')
        compiler = shlex.split(os.environ.get('CC', 'cc'), posix=os.name != 'nt')
        compiler = [part.strip('"') for part in compiler]
        self.assertTrue(shutil.which(compiler[0]), 'set CC to a portable C compiler')
        source = r'''
#include <assert.h>
#include "dm_shader_prep_policy.h"
int main(void) {
    assert(!dm_shader_prep_all(0));
    assert(!dm_shader_prep_all(""));
    assert(!dm_shader_prep_all("0"));
    assert(!dm_shader_prep_all("all-junk"));
    assert(dm_shader_prep_all("all"));
    assert(dm_shader_prep_workers(9, 0) == 2);
    assert(dm_shader_prep_workers(1, 0) == 1);
    assert(dm_shader_prep_workers(9, 1) == 1);
    assert(dm_shader_prep_workers(9, 999) == 2);
    assert(dm_shader_prep_limit(2, 0, 1, 0) == 2);
    assert(dm_shader_prep_limit(2, 1, 1, 0) == 1);
    assert(dm_shader_prep_limit(2, 2, 1, 0) == 0);
    assert(dm_shader_prep_limit(2, 3, 1, 0) == 0);
    assert(dm_shader_prep_limit(2, 0, 0, 0) == 0);
    assert(dm_shader_prep_limit(2, 0, 1, 1) == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='dm-shader-policy-') as directory:
            root = Path(directory)
            cfile, exe = root / 'test.c', root / ('test.exe' if os.name == 'nt' else 'test')
            cfile.write_text(source, encoding='utf-8')
            built = subprocess.run(compiler + ['-std=c11', '-Wall', '-Wextra', '-Werror',
                                   '-I', str(IOS), str(cfile), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
