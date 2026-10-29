"""Keep source compilation equivalent to the offline iOS shader contract."""
import platform
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]

class MslSourceOptions(unittest.TestCase):
    def test_runtime_and_prewarm_share_explicit_options(self):
        cases = [
            ('dm/gfx/nvn/nvn_mtl.m', 'src', 'source library loader'),
            ('dm/gfx/nvn/nvn_mtl.m', 't2', 'learned output rewrite'),
            ('dm/ios/Sources/dm_shader_prep.m', 'txt', 'source preparation'),
            ('dm/ios/Sources/dm_shader_prep.m', 't2', 'learned output preparation'),
            ('dm/gfx/gl/hle_gl.m', 'txt', 'GL source library loader'),
            ('dm/gfx/vk/hle_vk.m', 'txt', 'Vulkan source library loader'),
        ]
        for path, source, label in cases:
            with self.subTest(path=path, route=label):
                text = (ROOT/path).read_text(encoding='utf8')
                call = re.search(r'newLibraryWithSource:' + source + r'\s+options:([^\s]+)', text)
                self.assertIsNotNone(call, 'production source compile call not found')
                self.assertEqual(call[1], 'dm_msl_source_options()', label + ' must preserve the offline compiler options')

    def test_preparation_marker_names_the_compiler_contract(self):
        text = (ROOT/'dm/ios/Sources/dm_shader_prep.m').read_text(encoding='utf8')
        start = text.index('static NSString *marker(')
        end = text.index('int dm_shader_prep_begin', start)
        self.assertIn('DM_MSL_SOURCE_OPTIONS_TAG', text[start:end],
                      'old preparation markers must not suppress preparation after options change')

    @unittest.skipUnless(platform.system() == 'Darwin', 'Metal options objects require macOS')
    def test_native_options_without_a_gpu(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = str(Path(folder)/'source-options')
            build = subprocess.run(['clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                                    str(ROOT/'dm/gfx/tests/t_msl_source_options.m'),
                                    '-framework', 'Foundation', '-framework', 'Metal', '-o', exe],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([exe], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

if __name__ == '__main__':
    unittest.main()
