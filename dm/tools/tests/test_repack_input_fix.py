"""The input fix only replaces the host; game content stays local and unchanged."""
import hashlib
import importlib.util
import json
import pathlib
import plistlib
import struct
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/repack_input_fix.py'


class RepackInputFix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.ipa = self.root / 'original.ipa'
        self.shell = self.root / 'shell.zip'
        self.output = self.root / 'fixed.ipa'
        self.prefix = 'Payload/DmIOS.app/'
        self.host = bytes.fromhex('cffaedfe0c0000010000000002000000') + b'new host'
        spec = importlib.util.spec_from_file_location('repack_input_fix', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        with zipfile.ZipFile(self.ipa, 'w') as z:
            z.writestr(self.prefix + 'Info.plist', plistlib.dumps({'CFBundleExecutable': 'DmIOS', 'CFBundleIdentifier': 'test.wonder'}))
            z.writestr(self.prefix + 'DmIOS', b'old host')
            z.writestr(self.prefix + 'dm/shell_info.txt', 'KIND=ios\nGUEST=1\nENV=1\nGATES=svc spin\n')
            z.writestr(self.prefix + 'romfs/game.data', b'game content' * 10)
            z.writestr(self.prefix + 'Frameworks/Guest.framework/Guest', b'guest program')
            z.writestr(self.prefix + '_CodeSignature/CodeResources', b'old signature')
        self.write_shell(True)

    def write_shell(self, marked):
        with zipfile.ZipFile(self.shell, 'w') as z:
            z.writestr(self.prefix + 'DmIOS', self.host)
            z.writestr(self.prefix + 'dm/shell_info.txt', 'KIND=ios\nGUEST=1\nENV=1\nMEM=1\nGATES=svc spin\n')
            if marked:
                z.writestr(self.prefix + 'dm/input_features.json', json.dumps({
                    'feature': 'ios-independent-controllers-touch-v1',
                    'host_sha256': hashlib.sha256(self.host).hexdigest(),
                }))

    def test_replaces_host_preserves_game_and_identity(self):
        self.module.repack(self.ipa, self.shell, self.output)
        with zipfile.ZipFile(self.ipa) as old, zipfile.ZipFile(self.output) as new:
            for name in ('Info.plist', 'romfs/game.data', 'Frameworks/Guest.framework/Guest'):
                self.assertEqual(old.read(self.prefix + name), new.read(self.prefix + name))
            self.assertEqual(new.read(self.prefix + 'DmIOS'), self.host)
            self.assertIn(self.prefix + 'dm/input_features.json', new.namelist())
            self.assertNotIn(self.prefix + '_CodeSignature/CodeResources', new.namelist())
            self.assertEqual((new.getinfo(self.prefix + 'DmIOS').external_attr >> 16) & 0o777, 0o755)
            self.assertIsNone(new.testzip())

    def test_rejects_an_old_shell_without_the_compiled_fix_marker(self):
        self.write_shell(False)
        with self.assertRaisesRegex(ValueError, 'feature marker'):
            self.module.repack(self.ipa, self.shell, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_a_host_that_does_not_match_the_build_marker(self):
        with zipfile.ZipFile(self.shell, 'a') as z:
            z.writestr('unrelated', b'keep the archive valid')
        self.host = self.host + b'changed'
        # Rebuild the marker for different bytes, then put the original host under it.
        self.write_shell(True)
        with zipfile.ZipFile(self.shell) as z:
            entries = {n: z.read(n) for n in z.namelist()}
        entries[self.prefix + 'DmIOS'] = self.host[:-7]
        with zipfile.ZipFile(self.shell, 'w') as z:
            for name, data in entries.items():
                z.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.module.repack(self.ipa, self.shell, self.output)
        self.assertFalse(self.output.exists())

    def test_refuses_to_overwrite_original_or_existing_output(self):
        with self.assertRaisesRegex(ValueError, 'different'):
            self.module.repack(self.ipa, self.shell, self.ipa)
        self.output.write_bytes(b'keep this file')
        with self.assertRaises(FileExistsError):
            self.module.repack(self.ipa, self.shell, self.output)
        self.assertEqual(self.output.read_bytes(), b'keep this file')

    def test_regenerates_zip64_offsets_and_preserves_other_metadata(self):
        with zipfile.ZipFile(self.ipa, 'a') as z:
            entry = zipfile.ZipInfo(self.prefix + 'romfs/zip64.data')
            entry.extra = struct.pack('<HHQ', 1, 8, 0x12345678) + struct.pack('<HH4s', 0xcafe, 4, b'meta')
            z.writestr(entry, b'game data beyond a 4 GB offset')
        self.module.repack(self.ipa, self.shell, self.output)
        with zipfile.ZipFile(self.output) as z:
            # ZipFile regenerates ZIP64 size/offset fields for the new archive layout.
            self.assertEqual(z.getinfo(entry.filename).extra, struct.pack('<HH4s', 0xcafe, 4, b'meta'))
            self.assertEqual(z.read(entry.filename), b'game data beyond a 4 GB offset')

    def test_rejects_a_game_with_modules_embedded_in_the_old_host(self):
        with zipfile.ZipFile(self.ipa) as z:
            entries = {n: z.read(n) for n in z.namelist() if 'Guest.framework' not in n}
        with zipfile.ZipFile(self.ipa, 'w') as z:
            for name, data in entries.items():
                z.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'Guest framework'):
            self.module.repack(self.ipa, self.shell, self.output)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
