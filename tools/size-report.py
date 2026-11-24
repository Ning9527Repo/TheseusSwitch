#!/usr/bin/env python3
"""Report actual installed file sizes from a TheseusSwitch gzip-format deb."""
import argparse
import gzip
from pathlib import Path
from verify import ar_read, tar_read


def report(path):
    path = Path(path)
    ar = ar_read(path)
    files, _ = tar_read(ar['data.tar.gz'])
    total = sum(map(len, files.values()))
    print(f'DEB: {path.stat().st_size:,} bytes | payload gzip: {len(ar["data.tar.gz"]):,} bytes | installed file content: {total:,} bytes')
    print('Installed bytes   Standalone gzip estimate   Path')
    for name, data in sorted(files.items(), key=lambda x: -len(x[1])):
        print(f'{len(data):15,d}   {len(gzip.compress(data, mtime=0)):24,d}   {name}')
    print('Standalone gzip estimates are illustrative, not additive: the DEB compresses a single tar stream.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deb')
    report(parser.parse_args().deb)
