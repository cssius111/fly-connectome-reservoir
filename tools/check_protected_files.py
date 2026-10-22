"""Check the protected original experiment files against a local hash manifest.

The manifest (`artifacts/m1-2/protected-before.json`, named in AGENTS.md) is a local,
git-ignored file. This tool reads any (path, sha256) pairs it contains, in either of the
common layouts {"path": "sha256"} / {"path": {"sha256": ...}} or a list of
{"path": ..., "sha256": ...} objects, at any nesting depth, and compares every file's
current bytes with its recorded hash. It changes nothing.

Each file is compared in three forms: its bytes as they are, with CRLF normalised to
LF, and with LF expanded to CRLF. A match in either converted form means the content is
intact and only the line endings differ from when the manifest was written; for example,
the original experiment's results/ outputs were written by Python on Windows with CRLF,
while git stores and checks them out with LF. Byte-exact source checks such as
verify_results.py still need the source files with the line endings they were hashed with.

    python tools/check_protected_files.py D:\\Projects\\flybrain-lab\\artifacts\\m1-2\\protected-before.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r'^[0-9a-f]{64}$')


def pairs(node):
    """Yield (path, sha256) pairs from any supported manifest layout."""
    if isinstance(node, dict):
        path, digest = node.get('path'), node.get('sha256')
        if isinstance(path, str) and isinstance(digest, str) and SHA256.match(digest):
            yield path, digest
            return
        for key, value in node.items():
            if isinstance(value, str) and SHA256.match(value) and ('/' in key or '.' in key):
                yield key, value
            elif isinstance(value, dict) and isinstance(value.get('sha256'), str) \
                    and SHA256.match(value['sha256']) and 'path' not in value:
                yield key, value['sha256']
            else:
                yield from pairs(value)
    elif isinstance(node, list):
        for value in node:
            yield from pairs(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--root', type=Path, default=ROOT, help='checkout whose files are checked')
    args = parser.parse_args()
    found = dict(pairs(json.loads(args.manifest.read_text(encoding='utf-8'))))
    if not found:
        raise SystemExit('no (path, sha256) pairs found in ' + str(args.manifest))
    counts = {'byte-exact': 0, 'as LF': 0, 'as CRLF': 0}
    failures = []
    for rel, digest in sorted(found.items()):
        path = args.root / rel
        if not path.exists():
            failures.append(rel + ': missing')
            continue
        data = path.read_bytes()
        lf = data.replace(b'\r\n', b'\n')
        forms = {'byte-exact': data, 'as LF': lf, 'as CRLF': lf.replace(b'\n', b'\r\n')}
        match = next((name for name, form in forms.items()
                      if hashlib.sha256(form).hexdigest() == digest), None)
        if match is None:
            failures.append('%s: no form matches (recorded %s..., byte-exact %s...)'
                            % (rel, digest[:12], hashlib.sha256(data).hexdigest()[:12]))
            continue
        counts[match] += 1
        if match != 'byte-exact':
            print('content matches %s, line endings differ from the manifest: %s' % (match, rel))
    matched = sum(counts.values())
    print('%d of %d protected files match (%s)' % (matched, len(found),
          ', '.join('%s %d' % (k, v) for k, v in counts.items())))
    for line in failures:
        print('FAIL', line)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
