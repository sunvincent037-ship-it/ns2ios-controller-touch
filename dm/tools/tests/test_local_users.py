"""Portable tests of the actual account hooks and save-mount path selection.

CC may name a compiler command (for example 'zig cc'); the default is cc.
Only the Apple host prelude and the filesystem transaction boundary are replaced.
"""
import importlib.util
import os
import pathlib
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
HOST = ROOT / 'dm/host'
PRELUDE = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <assert.h>
typedef uint32_t Result;
#define RES_OK 0u
#define RES_FAIL 0x2a2u
#define HLE_FORCE(mangled, why, ret, cname, ...) ret cname(__VA_ARGS__)
#define LOG(...) ((void)0)
// The Windows CRT converts environment strings through its code page; supply exact UTF-8 bytes for nickname fixtures.
static const char *test_nickname;
static char *test_getenv(const char *name) {
    return test_nickname && !strcmp(name, "DM_NICK") ? (char *)test_nickname : getenv(name);
}
#define getenv test_getenv
static void die(const char *fmt, ...) { (void)fmt; abort(); }
static void hle_signal_system_event(void *ev) { (void)ev; }
static size_t test_strlcpy(char *dst, const char *src, size_t cap) {
    size_t n = strlen(src);
    if (cap) { size_t k = n < cap - 1 ? n : cap - 1; memcpy(dst, src, k); dst[k] = 0; }
    return n;
}
#define strlcpy test_strlcpy
static char mounted[2048];
static int mount_calls;
static Result mount_ex(const char *name, const char *dir, int ro, int txn) {
    assert(name && !ro && txn); mount_calls++; strlcpy(mounted, dir, sizeof mounted); return RES_OK;
}
'''


def mount_save_source():
    source = (HOST / 'hle_fs.c').read_text(encoding='utf-8')
    start = source.index('HLE_FORCE("_ZN2nn2fs13MountSaveDataEPKcRKNS_7account3UidE"')
    body = source.index('{', start)
    depth = 1
    end = body + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class LocalUsers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = os.environ.get('CC', 'cc')
        cls.cc = shlex.split(compiler, posix=os.name != 'nt')
        cls.cc = [p.strip('"') for p in cls.cc]
        if not shutil.which(cls.cc[0]):
            raise unittest.SkipTest('portable C compiler unavailable; set CC')
        cls.tmp = tempfile.TemporaryDirectory(prefix='dm-local-users-')
        work = pathlib.Path(cls.tmp.name)
        source = (HOST / 'hle_account.c').read_text(encoding='utf-8')
        source = source.replace('#include "hle.h"', PRELUDE, 1)
        source += '\n' + mount_save_source()
        source += '\n' + (HOST / 'tests/t_local_users.c').read_text(encoding='utf-8')
        cfile = work / 'account_test.c'
        cfile.write_text(source, encoding='utf-8')
        cls.exe = work / ('account_test.exe' if os.name == 'nt' else 'account_test')
        command = cls.cc + ['-std=c11', '-Wall', '-Wextra', '-Werror',
                           '-Wno-unused-function', '-I', str(HOST), str(cfile), '-o', str(cls.exe)]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode:
            raise AssertionError('C harness compilation failed:\n' + result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, case, users=None, save='/saves/game', nick=None, expected_count=None):
        env = dict(os.environ)
        for key, value in [('DM_LOCAL_USERS', users), ('DM_SAVE', save), ('DM_NICK', nick)]:
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        args = [str(self.exe), case]
        if expected_count is not None:
            args.append(str(expected_count))
        result = subprocess.run(args, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_default_preserves_primary_identity(self):
        self.run_case('enumerate', expected_count=1)

    def test_opt_in_enumerates_distinct_users(self):
        for count in range(1, 9):
            with self.subTest(count=count):
                self.run_case('enumerate', users=str(count), expected_count=count)

    def test_invalid_runtime_counts_keep_single_user_default(self):
        for value in ['', '0', '9', '-1', '2junk', ' 2', '+2', '02', '99999999999999999']:
            with self.subTest(value=value):
                self.run_case('enumerate', users=value, expected_count=1)

    def test_open_close_and_last_opened_track_real_handles(self):
        self.run_case('lifecycle', users='2')

    def test_additional_selection_respects_open_users_and_exclusions(self):
        self.run_case('selection', users='2')

    def test_local_selection_does_not_create_online_identity(self):
        self.run_case('online', users='2')

    def test_unknown_uids_and_handles_fail(self):
        self.run_case('invalid', users='2')

    def test_primary_and_secondary_save_backings_are_siblings(self):
        self.run_case('saves', users='2', save='/saves/game///')

    def test_unknown_uid_cannot_mount_another_users_save(self):
        self.run_case('unknown_save', users='2')

    def test_save_paths_fail_before_any_truncation(self):
        self.run_case('overflow_save', users='2', save='x' * 1024)
        self.run_case('secondary_overflow', users='2', save='x' * 1013)

    def test_custom_primary_nickname_is_preserved(self):
        self.run_case('nickname', users='2', nick='Alex')

    def test_secondary_nickname_keeps_complete_utf8_prefix(self):
        for nickname, prefix_bytes in [('a' * 29 + '\u4e2d', 29),
                                       ('a' * 27 + '\u4e2d', 30),
                                       ('a' * 28 + '\u00e9' + 'x', 30),
                                       ('a' * 27 + '\U0001f600', 27)]:
            with self.subTest(nickname=nickname):
                self.run_case('nickname_utf8', users='2', nick=nickname.encode('utf-8').hex(),
                              expected_count=prefix_bytes)


class LocalUserPackaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('nxn_pack_local_users', ROOT / 'scripts/nxn_pack.py')
        cls.pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.pack)

    def test_only_explicit_profile_opts_in(self):
        self.assertFalse(any(line.startswith('DM_LOCAL_USERS=') for line in self.pack.env_for({})))
        for count in range(1, 9):
            self.assertIn('DM_LOCAL_USERS=%d' % count, self.pack.env_for({'local_users': [str(count)]}))

    def test_invalid_profile_counts_fail(self):
        for value in ['', '0', '9', '-1', '2junk', '+2', '02', '999999999999999999']:
            with self.subTest(value=value):
                with self.assertRaisesRegex((ValueError, SystemExit), 'local_users'):
                    self.pack.env_for({'local_users': [value]})

    def test_measured_allocator_row_uses_existing_build_and_cut_guards(self):
        source = (HOST / 'hle_uemalloc.c').read_text(encoding='utf-8')
        self.assertRegex(source, r'"9e9d887d59f7f7db176b35e3379258b9",\s*"Minecraft Dungeons II 1\.1\.1\.0",\s*UE5_6,\s*0x9979228,\s*0x85b68a8,\s*0x143b0')
        self.assertIn('!strcmp(g_mod[i].build_id, k_ue[k].build)', source)
        self.assertIn('*(uint32_t *)(b + k_ue[k].cut) != 0xd503201f', source)


if __name__ == '__main__':
    unittest.main()
