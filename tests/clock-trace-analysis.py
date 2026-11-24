#!/usr/bin/env python3
"""Read a TheseusClockTrace log, without including any source device identifiers."""
import json, re, sys
from pathlib import Path

def analyze(path):
    prior = None
    reorders = mismatches = 0
    release_events = []
    for line in Path(path).read_text(errors='replace').splitlines():
        m = re.match(r'\[TS\] \+(\d+)ms (\w+) (.*)', line)
        if not m: continue
        t, kind, raw = m.groups()
        try: data = json.loads(raw)
        except json.JSONDecodeError: continue
        if kind == 'ROWS':
            current = [r['overlay'] for r in data]
            if prior is not None and prior != current: reorders += 1
            prior = current
        elif kind == 'VALUE' and data['overlay'] != data['native']:
            mismatches += 1
        elif kind == 'ADD_ANIM' and any('finishPress' in frame for frame in data.get('stack', [])):
            release_events.append((int(t), data['owner'].split('@')[0], data.get('key')))
    return dict(visible_order_changes=reorders, mismatched_value_samples=mismatches, release_animation_events=release_events)

if __name__ == '__main__':
    print(json.dumps(analyze(sys.argv[1]), indent=2))
