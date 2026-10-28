#!/usr/bin/env python3
"""Put a newly compiled input-fix host into an existing IPA, on Windows or macOS.

The game, shaders, identity and Guest framework are copied from the existing IPA.
The replacement shell must carry the checksum marker written by input-fix.yml.
The output is unsigned and must be signed by the user's sideloading tool.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import tempfile
import zipfile

FEATURE = 'ios-independent-controllers-touch-v1'


def app_prefix(archive):
    apps = {n.split('/')[1] for n in archive.namelist()
            if n.startswith('Payload/') and len(n.split('/')) > 2 and n.split('/')[1].endswith('.app')}
    if len(apps) != 1:
        raise ValueError('archive must contain exactly one Payload app')
    return 'Payload/' + apps.pop() + '/'


def without_zip64(extra):
    # Entries beyond 4 GB may carry an offset-only ZIP64 field. That offset is
    # tied to the old layout; ZipFile must generate it again for the new archive.
    kept, offset = [], 0
    while offset + 4 <= len(extra):
        tag, size = struct.unpack_from('<HH', extra, offset)
        end = offset + 4 + size
        if end > len(extra):
            raise ValueError('malformed ZIP entry extra metadata')
        if tag != 1:
            kept.append(extra[offset:end])
        offset = end
    return b''.join(kept) + extra[offset:]


def repack(ipa, shell, output):
    ipa, shell, output = (Path(p).resolve() for p in (ipa, shell, output))
    if output in (ipa, shell):
        raise ValueError('output must be different from the original IPA and shell')
    if output.exists():
        raise FileExistsError(output)
    with zipfile.ZipFile(shell) as replacement:
        prefix = app_prefix(replacement)
        try:
            marker_data = replacement.read(prefix + 'dm/input_features.json')
        except KeyError as error:
            raise ValueError('shell has no compiled input-fix feature marker') from error
        marker = json.loads(marker_data)
        if marker.get('feature') != FEATURE:
            raise ValueError('shell has the wrong input-fix feature marker')
        host = replacement.read(prefix + 'DmIOS')
        if hashlib.sha256(host).hexdigest() != marker.get('host_sha256'):
            raise ValueError('replacement host checksum does not match its build marker')
        if host[:4] != bytes.fromhex('cffaedfe') or host[4:8] != bytes.fromhex('0c000001'):
            raise ValueError('replacement host is not an ARM64 Mach-O executable')
        shell_info = replacement.read(prefix + 'dm/shell_info.txt')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, stage_name = tempfile.mkstemp(prefix=output.stem + '-', suffix='.partial', dir=output.parent)
    os.close(fd)
    stage = Path(stage_name)
    try:
        with zipfile.ZipFile(ipa) as old, zipfile.ZipFile(stage, 'w', allowZip64=True) as new:
            prefix = app_prefix(old)
            plist = plistlib.loads(old.read(prefix + 'Info.plist'))
            if plist.get('CFBundleExecutable') != 'DmIOS':
                raise ValueError('original IPA is not a DmIOS game')
            if prefix + 'Frameworks/Guest.framework/Guest' not in old.namelist():
                raise ValueError('original IPA has no separate Guest framework; its host cannot be replaced')
            try:
                old_stamp = old.read(prefix + 'dm/shell_info.txt').decode('utf-8')
            except KeyError as error:
                raise ValueError('original IPA has no shell capability stamp') from error
            old_caps = dict(line.split('=', 1) for line in old_stamp.splitlines() if '=' in line)
            if any(old_caps.get(k) != v for k, v in (('KIND', 'ios'), ('GUEST', '1'), ('ENV', '1'))):
                raise ValueError('original IPA does not use the supported game-free shell format')
            changes = {'DmIOS': host, 'dm/input_features.json': marker_data, 'dm/shell_info.txt': shell_info}
            for entry in old.infolist():
                name = entry.filename
                if name.startswith(prefix):
                    relative = name[len(prefix):]
                    if relative in changes or relative.startswith('_CodeSignature/') or relative == 'embedded.mobileprovision':
                        continue
                # Copy uncompressed bytes through ZipFile so every original CRC is checked.
                # Keep compression and metadata, including the Guest framework's executable bit.
                updated = copy.copy(entry)
                updated.extra = without_zip64(entry.extra)
                with old.open(entry) as source, new.open(updated, 'w', force_zip64=entry.file_size >= 2**31) as dest:
                    shutil.copyfileobj(source, dest, length=1024 * 1024)
            for relative, data in changes.items():
                entry = zipfile.ZipInfo(prefix + relative)
                entry.create_system = 3
                entry.external_attr = (0o100755 if relative == 'DmIOS' else 0o100644) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                new.writestr(entry, data)
        with zipfile.ZipFile(stage) as check:
            bad = check.testzip()
            if bad:
                raise ValueError('output archive CRC failed: ' + bad)
        # Publish the verified file without a second multi-GB copy. Windows rename
        # and POSIX link both refuse an existing destination; replace would not.
        if os.name == 'nt':
            stage.rename(output)
        else:
            os.link(stage, output)
    finally:
        stage.unlink(missing_ok=True)
    return {'ipa': str(output), 'bytes': output.stat().st_size, 'feature': FEATURE,
            'host_sha256': marker['host_sha256'], 'all_zip_crcs_passed': True,
            'signing': 'Requires user sideload signing', 'device_test': 'Not performed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, help='existing local game IPA')
    parser.add_argument('shell', type=Path, help='controller-touch-shell.zip built by input-fix.yml')
    parser.add_argument('output', type=Path, help='new IPA path; must not already exist')
    args = parser.parse_args()
    try:
        result = repack(args.ipa, args.shell, args.output)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, 'Repack failed: %s\n' % error)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
