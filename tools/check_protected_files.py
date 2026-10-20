"""Check the protected original experiment files against a local hash manifest.

The manifest (`artifacts/m1-2/protected-before.json`, named in AGENTS.md) is a local,
git-ignored file. This tool reads any (path, sha256) pairs it contains, in either of the
common layouts {"path": "sha256"} / {"path": {"sha256": ...}} or a list of
{"path": ..., "sha256": ...} objects, at any nesting depth, and compares every file's
current bytes with its recorded hash. It changes nothing.

A file whose working copy was expanded to CRLF by core.autocrlf is reported as
"LF content matches": its committed content is intact, but byte-exact checks such as
verify_results.py will fail until it is checked out with LF.

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
    exact = lf_only = 0
    failures = []
    for rel, digest in sorted(found.items()):
        path = args.root / rel
        if not path.exists():
            failures.append(rel + ': missing')
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() == digest:
            exact += 1
        elif hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest() == digest:
            lf_only += 1
            print('LF content matches, working copy has CRLF:', rel)
        else:
            failures.append(rel + ': hash differs')
    print('%d of %d protected files match byte-exactly' % (exact, len(found)))
    if lf_only:
        print('%d match only after CRLF -> LF; re-check them out with LF before verify_results.py' % lf_only)
    for line in failures:
        print('FAIL', line)
    return 1 if failures or lf_only else 0


if __name__ == '__main__':
    sys.exit(main())
