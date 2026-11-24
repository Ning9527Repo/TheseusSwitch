#!/usr/bin/env python3
"""Portable standalone source contracts; never compiles or invokes network tools."""
import hashlib
import json
import plistlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT/'packaging/config.json').read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path):
    return Path(path).relative_to(ROOT).as_posix()


def discover():
    # This extraction retains only switch and its shared dependencies.
    vendor = sorted((ROOT/'Vendor/Theseus/Sources/Theseus').rglob('*.swift'))
    assert not any(p.name in ('TheseusSlider.swift', 'TheseusTabBar.swift') for p in vendor)
    swift = vendor
    return {'vendor_swift': vendor, 'switch_swift': swift,
            'swift': swift+[ROOT/'src/TheseusBridge.swift', ROOT/'src/TheseusBundle.swift'],
            'core': sorted((ROOT/'src').glob('*.m')),
            'theseus_metal': sorted((ROOT/'Vendor/Theseus/Sources/Theseus').rglob('*.metal'))}


def vendor_manifest():
    path = ROOT/'Vendor/manifest.json'
    manifest = json.loads(path.read_text())
    actual = {rel(p) for p in (ROOT/'Vendor/Theseus').rglob('*') if p.is_file() and p.name != 'UPSTREAM.json'}
    if set(manifest) != actual or len(actual) != 35:
        raise ValueError('Pinned upstream file coverage mismatch')
    patches = json.loads((ROOT/'Vendor/local-patches.json').read_text())
    if not set(patches) <= set(manifest):
        raise ValueError('Unknown patched file')
    for name, digest in manifest.items():
        patch = patches.get(name)
        if patch and patch['upstream_sha256'] != digest:
            raise ValueError('Patch provenance mismatch: '+name)
        expected = patch['patched_sha256'] if patch else digest
        if sha256(ROOT/name) != expected:
            raise ValueError('Source hash mismatch: '+name)
    upstream = json.loads((ROOT/'Vendor/Theseus/UPSTREAM.json').read_text())
    if upstream['revision'] != '71ca1c127a4e7fe3387361f160c4890dbd427f66':
        raise ValueError('Unexpected upstream revision')
    return {'files': len(actual), 'verified': True, 'manifest_sha256': sha256(path), 'upstream': upstream, 'local_patches': patches}


def check():
    sources = discover()
    counts = {k: len(v) for k, v in sources.items()}
    expected = {'vendor_swift': 31, 'switch_swift': 31, 'swift': 33, 'core': 3, 'theseus_metal': 1}
    if counts != expected:
        raise ValueError('Missing or unexpected source: '+str(counts))
    for p in ROOT.rglob('*.plist'):
        plistlib.loads(p.read_bytes())
    assert plistlib.loads((ROOT/'src/Filter.plist').read_bytes())['Filter']['Bundles'] == ['com.apple.UIKit']
    forbidden = re.compile(r'Glassify|NGDock|NGClearDockView|NGWallpaper|enabledDock|dockStyle|NGRefreshDock|NGGlassComponent')
    for p in [*(ROOT/'src').glob('*'), ROOT/'tools/build.py']:
        if forbidden.search(p.read_text()):
            raise ValueError('Unwanted integration reference: '+rel(p))
    assert not any(p.suffix.lower() == '.png' for p in ROOT.rglob('*') if p.is_file() and not {'build', 'dist'} & set(p.relative_to(ROOT).parts)), 'Unexpected PNG source asset'
    assert not (ROOT/'prefs').exists()
    assert not (ROOT/'src/NGPreferences.m').exists()
    assert all('preferenceloader' not in v['depends'].lower() for v in CONFIG['variants'].values())
    assert 'CFPreferences' not in (ROOT/'src/NGResources.m').read_text()
    assert 'NGPreferencesReload' not in (ROOT/'src/Tweak.m').read_text()
    assert not any(line.startswith('Icon:') for line in (ROOT/'control').read_text().splitlines())
    bridge = (ROOT/'src/TheseusBridge.swift').read_text()
    assert 'private let toggle = TheseusSwitch()' in bridge
    assert not re.search(r'toggle\.(configuration|layout|onTintColor|tintColor)\s*=', bridge)
    native = (ROOT/'src/NGSwitch.m').read_text()
    assert 'CGSizeMake(63,28)' in native
    hooks = (ROOT/'src/Tweak.m').read_text()
    for selector in ('layoutSubviews','didMoveToWindow','didMoveToSuperview','setOn:','setOn:animated:','setEnabled:','setHidden:','setAlpha:','setUserInteractionEnabled:'):
        assert '@selector('+selector+')' in hooks,selector
    assert 'dlsym' in hooks and 'MSHookMessageEx' in hooks
    assert not (ROOT/'Vendor/Glassify').exists()
    workflows = sorted((ROOT/'.github/workflows').glob('*.yml'))
    assert len(workflows) == 1 and 'workflow_dispatch:' in workflows[0].read_text()
    assert not re.search(r'^\s+(push|pull_request|schedule):', workflows[0].read_text(), re.M)
    return {'status':'passed','counts':counts,'vendor':vendor_manifest(),'preference_keys':[], 'always_enabled':True,
            'sources':{k:[rel(p) for p in v] for k,v in sources.items()},
            'native_build_executed':False,'device_validation_executed':False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    args = parser.parse_args()
    result = check()
    text = json.dumps(result,indent=2)+'\n'
    if args.output:
        output = Path(args.output); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(text)
    print(text)
