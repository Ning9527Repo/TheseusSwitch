#!/usr/bin/env python3
"""Verify FINAL extracted deb, Mach-O ABI, imports, dependencies and native signature."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import struct
import subprocess
import tarfile
import tempfile
from project import CONFIG, sha256

ROOT_HIDE = '@loader_path/.jbroot/usr/lib/libroothide.dylib'
PREFERENCES = '/System/Library/PrivateFrameworks/Preferences.framework/Preferences'
MACH_MAGICS = (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def ar_read(path):
    data = Path(path).read_bytes()
    require(data[:8] == b'!<arch>\n', 'Invalid ar magic')
    off, members = 8, {}
    while off < len(data):
        h = data[off:off+60]
        require(len(h) == 60 and h[58:60] == b'`\n', 'Invalid ar header')
        name = h[:16].decode('ascii').strip().rstrip('/')
        size = int(h[48:58].decode('ascii').strip())
        require(size >= 0 and off+60+size <= len(data), 'Invalid ar size')
        require(name not in members, 'Duplicate ar member')
        members[name] = data[off+60:off+60+size]
        off += 60 + size + (size % 2)
    require(off == len(data), 'Trailing ar data')
    require(list(members) == ['debian-binary', 'control.tar.gz', 'data.tar.gz'], 'Unexpected ar members')
    require(members['debian-binary'] == b'2.0\n', 'Wrong Debian version')
    return members


def tar_read(data):
    raw = gzip.decompress(data)
    off = 0
    while off+512 <= len(raw) and raw[off:off+512] != b'\0'*512:
        head = raw[off:off+512]
        require(head[257:263] == b'ustar\0', 'Archive must be USTAR')
        require(head[156:157] in (b'0', b'\0', b'5'), 'PAX/GNU extensions, links or device member forbidden')
        size = int(head[124:136].rstrip(b'\0 ').lstrip(b' ') or b'0', 8)
        off += 512 + ((size+511)//512)*512
    files, metadata = {}, []
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
        for m in tar:
            name = m.name.removeprefix('./')
            p = PurePosixPath(name)
            require(name and not p.is_absolute() and '..' not in p.parts and '\\' not in name, 'Unsafe tar member')
            require(m.uid == 0 and m.gid == 0, 'Payload must be owned by root')
            require(m.isdir() or m.isfile(), 'Links/special files forbidden')
            require(name not in {x['path'] for x in metadata}, 'Duplicate payload path')
            metadata.append({'path': name, 'size': m.size, 'mode': oct(m.mode), 'type': 'directory' if m.isdir() else 'file'})
            if m.isfile():
                files[name] = tar.extractfile(m).read()
    return files, metadata


def cstring(data, start, end):
    require(0 <= start < end <= len(data), 'Out-of-bounds Mach-O string')
    pos = data.find(b'\0', start, end)
    require(pos >= 0, 'Unterminated Mach-O string')
    return data[start:pos].decode('utf-8')


def macho(data, expected_arch):
    require(data[:4] == b'\xcf\xfa\xed\xfe', 'Expected thin native little-endian Mach-O 64, never fat/relabelled')
    _, cpu, sub, ftype, ncmds, sizecmds, flags, _ = struct.unpack_from('<8I', data)
    require(cpu == 0x100000c, 'Wrong CPU')
    require(sub == CONFIG['variants'][expected_arch]['subtype'], f'Wrong {expected_arch} CPU subtype: {sub:#010x}')
    require(flags & 0x80, 'MH_TWOLEVEL required; flat namespace forbidden')
    require(32+sizecmds <= len(data), 'Invalid load command region')
    off, deps, rpaths, identity, signature, symtab = 32, [], [], None, None, None
    minimum, build_platform = None, None
    for _ in range(ncmds):
        require(off+8 <= 32+sizecmds, 'Truncated load command')
        cmd, size = struct.unpack_from('<II', data, off)
        require(size >= 8 and off+size <= 32+sizecmds, 'Invalid load command')
        if cmd in (0xc, 0xd, 0x80000018, 0x8000001f, 0x80000023):
            noff = struct.unpack_from('<I', data, off+8)[0]
            name = cstring(data, off+noff, off+size)
            if cmd == 0xd:
                identity = name
            else:
                deps.append(name)
        elif cmd == 0x8000001c:
            rpaths.append(cstring(data, off+struct.unpack_from('<I', data, off+8)[0], off+size))
        elif cmd == 0x1d:
            pos, length = struct.unpack_from('<II', data, off+8)
            require(length > 0 and pos+length <= len(data), 'Invalid code signature region')
            signature = {'offset': pos, 'bytes': length}
        elif cmd == 0x2:
            symtab = struct.unpack_from('<4I', data, off+8)
        elif cmd == 0x32:
            build_platform, minimum = struct.unpack_from('<II', data, off+8)
        elif cmd == 0x25:
            minimum = struct.unpack_from('<I', data, off+8)[0]
            build_platform = 2
        off += size
    require(off == 32+sizecmds, 'Mach-O load command size mismatch')
    require(signature is not None, 'Missing LC_CODE_SIGNATURE')
    require(minimum is not None and minimum == 0x000f0000 and build_platform == 2, 'Deployment target must be iOS 15.0 device')
    imports = []
    if symtab:
        so, ns, stro, ss = symtab
        require(so+ns*16 <= len(data) and stro+ss <= len(data), 'Invalid symbol table')
        for i in range(ns):
            idx, typ, sect, desc, value = struct.unpack_from('<IBBHQ', data, so+16*i)
            if typ & 0xe0 or not (typ & 1) or (typ & 0xe) != 0 or value != 0:
                continue
            name = cstring(data, stro+idx, stro+ss)
            ordinal = desc >> 8
            require(1 <= ordinal <= len(deps), 'Unbound/dynamic-lookup import: ' + name)
            require(name != '_MSHookMessageEx', 'MSHookMessageEx must use dlsym, not unresolved import')
            imports.append({'symbol': name, 'dependency': deps[ordinal-1]})
    return {'cpu': hex(cpu), 'subtype': f'0x{sub:08x}', 'filetype': ftype, 'install_name': identity,
            'dependencies': deps, 'rpaths': rpaths, 'signature': signature, 'imports': imports,
            'deployment': '15.0', 'platform': 'iOS'}


def native_sign_verify(path):
    require(platform.system() == 'Darwin', 'Native strict codesign verification requires macOS')
    cmd = ['codesign', '--verify', '--strict', '--verbose=4', str(path)]
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(p.returncode == 0, 'Native strict signature rejected: ' + str(path) + '\n' + p.stderr)
    return {'command': cmd, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}


def verify(path, arch, native=True):
    variant = CONFIG['variants'][arch]
    prefix = variant['prefix']
    base = prefix+'/' if prefix else ''
    ar = ar_read(path)
    ctl, control_members = tar_read(ar['control.tar.gz'])
    files, members = tar_read(ar['data.tar.gz'])
    require(set(ctl) == {'control', 'postinst', 'md5sums'}, 'Unexpected maintainer scripts/control members')
    control = dict(line.split(': ', 1) for line in ctl['control'].decode().splitlines() if ': ' in line)
    expected = {'Package': CONFIG['package'], 'Version': CONFIG['version'], 'Name': CONFIG['name'],
                'Architecture': variant['architecture'], 'Author': CONFIG['author'], 'Maintainer': CONFIG.get('maintainer', 'Ning'),
                'Depends': variant['depends']}
    for key, value in expected.items():
        require(control.get(key) == value, 'Wrong control '+key+': '+str(control.get(key)))
    post = ctl['postinst'].decode()
    commands = '\n'.join(line for line in post.splitlines() if line.strip() and not line.lstrip().startswith('#'))
    require(commands.strip() == 'set -e\nexit 0', 'postinst must not signal processes or mutate external directories')
    require(not re.search(r'kill|respring|sbreload|launchctl', commands, re.I), 'Forbidden installer process action')
    md5sums = dict(line.split('  ', 1)[::-1] for line in ctl['md5sums'].decode().splitlines())
    require(set(md5sums) == set(files), 'md5sums payload coverage mismatch')
    for name, data in files.items():
        require(hashlib.md5(data).hexdigest() == md5sums[name], 'Payload checksum mismatch: '+name)
    main = base+'Library/MobileSubstrate/DynamicLibraries/TheseusSwitch.dylib'
    filt = base+'Library/MobileSubstrate/DynamicLibraries/TheseusSwitch.plist'
    resources = base+'Library/Application Support/TheseusSwitch/TheseusSwitchResources.bundle'
    resource_files = {resources+'/default.metallib', resources+'/Info.plist'}
    required = {main, filt, *resource_files}
    require(required <= set(files), 'Missing payload files: '+str(sorted(required-set(files))))
    for name in files:
        require(name in required or name.startswith(base+'usr/share/doc/'+CONFIG['package']+'/'),
                'Unexpected installed payload file: '+name)
    require('preferenceloader' not in control['Depends'].lower(), 'Unexpected settings dependency')
    dylibs = [name for name in files if name.endswith('.dylib')]
    require(dylibs == [main], 'Exactly one main dylib required')
    require(len([name for name in files if name.endswith('.metallib')]) == 1, 'Exactly one original Metal library required')
    for name in resource_files:
        if name.endswith('.metallib'):
            require(files[name][:4] == b'MTLB', 'Invalid Metal library: '+name)
    require('Icon' not in control, 'Unexpected package icon metadata')
    require(not any(name.lower().endswith('.png') for name in files), 'Unexpected PNG payload')
    require(plistlib.loads(files[filt]).get('Filter', {}).get('Bundles'), 'Empty filter')
    details = []
    with tempfile.TemporaryDirectory(prefix='theseusswitch-final-') as tmp:
        root = Path(tmp)
        for name, data in files.items():
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
            mode = next(int(m['mode'], 8) for m in members if m['path'] == name)
            dest.chmod(mode)
        machos = [name for name, data in files.items() if data[:4] in MACH_MAGICS]
        require(set(machos) == {main}, 'Unexpected/missing packaged Mach-O')
        for name in machos:
            item = macho(files[name], arch)
            require(item['filetype'] == 6, 'Wrong Mach-O file type '+name)
            require(ROOT_HIDE in item['dependencies'] if arch == 'arm64e' else ROOT_HIDE not in item['dependencies'],
                    'RootHide runtime dependency mismatch '+name)
            if name == main:
                require(b'NGTheseusSwitch\x00' in files[name], 'Theseus switch bridge missing')
                require(b'NGClearDockView\x00' not in files[name], 'Unexpected desktop integration')
                require(item['install_name'] == '@rpath/TheseusSwitch.dylib', 'Wrong main install name')
                require(any('libswiftCore.dylib' in p for p in item['dependencies']), 'Main must link actual Swift runtime')
                for framework in CONFIG['frameworks']:
                    require(any('/'+framework+'.framework/' in p for p in item['dependencies']), 'Missing linked framework '+framework)
            require(PREFERENCES not in item['dependencies'], 'Unexpected private settings framework')
            for dep in item['dependencies']:
                require(dep == ROOT_HIDE or dep.startswith('/System/Library/') or dep.startswith('/usr/lib/'),
                        'Unexpected runtime install name '+dep)
                require('/Applications/Xcode' not in dep and '.tbd' not in dep, 'SDK/link stub leaked into install name')
            for rp in item['rpaths']:
                require(rp in ('/usr/lib/swift', '@loader_path', '@loader_path/Frameworks'), 'Build path leaked into rpath '+rp)
            if native:
                item['native_strict_signature'] = native_sign_verify(root / name)
            else:
                item['native_strict_signature'] = {'status': 'not_run', 'reason': 'structural-only mode requested'}
            item['path'] = name
            item['sha256'] = hashlib.sha256(files[name]).hexdigest()
            details.append(item)
    return {'status': 'passed' if native else 'structural_only', 'package': Path(path).name, 'sha256': sha256(path),
            'bytes': Path(path).stat().st_size, 'variant': arch, 'control': control, 'mach_o': details,
            'members': members, 'control_members': control_members, 'preference_keys': [], 'always_enabled': True}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('deb'); p.add_argument('--arch', choices=CONFIG['variants'], required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--structural-only', action='store_true', help='Does not claim native signature verification')
    args = p.parse_args()
    try:
        result = verify(args.deb, args.arch, not args.structural_only)
    except Exception as e:
        result = {'status': 'failed', 'package': args.deb, 'variant': args.arch, 'error': str(e)}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('members','mach_o','control_members')}, indent=2))
    raise SystemExit(0 if result['status'] in ('passed','structural_only') else 1)
