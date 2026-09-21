"""Compare two kinematic traces bit-for-bit and locate the first divergence.

Used to accept the M1.8-B1 refactor on exact identity rather than on a tolerance.

    python tools/kinematics_diff.py artifacts/m1_8_b1/pre-b1-trace.json \
                                    artifacts/m1_8_b1/post-b1-trace.json
"""
import argparse
import json
from pathlib import Path
import sys


def compare(before, after):
    findings = []
    names = [s['scenario'] for s in before['scenarios']]
    if names != [s['scenario'] for s in after['scenarios']]:
        return [{'scenario': '*', 'kind': 'scenario_set_differs'}]
    for old, new in zip(before['scenarios'], after['scenarios']):
        name = old['scenario']
        if old['fields'] != new['fields']:
            findings.append({'scenario': name, 'kind': 'field_set_differs'})
            continue
        if len(old['rows']) != len(new['rows']):
            findings.append({'scenario': name, 'kind': 'tick_count_differs',
                             'before': len(old['rows']), 'after': len(new['rows'])})
            continue
        for tick, (a, b) in enumerate(zip(old['rows'], new['rows'])):
            if a != b:
                column = next(i for i, (x, y) in enumerate(zip(a, b)) if x != y)
                label = old['fields'][column] if column < len(old['fields']) else 'label[%d]' % column
                findings.append({'scenario': name, 'kind': 'first_divergence', 'tick': tick,
                                 'column': label, 'before': a[column], 'after': b[column]})
                break
        if old['rng_final_states'] != new['rng_final_states']:
            changed = [k for k in old['rng_final_states']
                       if old['rng_final_states'][k] != new['rng_final_states'].get(k)]
            findings.append({'scenario': name, 'kind': 'rng_call_order_changed',
                             'streams': changed})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding='utf-8'))
    after = json.loads(args.after.read_text(encoding='utf-8'))
    findings = compare(before, after)
    ticks = sum(s['ticks'] for s in before['scenarios'])
    result = {'before': str(args.before), 'after': str(args.after),
              'scenarios': len(before['scenarios']), 'total_ticks': ticks,
              'before_combined_sha256': before['combined_sha256'],
              'after_combined_sha256': after['combined_sha256'],
              'bit_identical': not findings and before['combined_sha256'] == after['combined_sha256'],
              'rng_call_order_unchanged': all(
                  a['rng_final_states'] == b['rng_final_states']
                  for a, b in zip(before['scenarios'], after['scenarios'])),
              'per_scenario': [{'scenario': a['scenario'], 'ticks': a['ticks'],
                                'identical': a['trace_sha256'] == b['trace_sha256'],
                                'sha256': a['trace_sha256']}
                               for a, b in zip(before['scenarios'], after['scenarios'])],
              'findings': findings}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'per_scenario'}, indent=1))
    for row in result['per_scenario']:
        print('  %-22s %5d ticks  identical=%s  %s' % (row['scenario'], row['ticks'],
                                                       row['identical'], row['sha256'][:16]))
    return 0 if result['bit_identical'] else 1


if __name__ == '__main__':
    sys.exit(main())
