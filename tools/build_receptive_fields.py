"""Build data/receptive_fields_v1.npz, the M3.4 receptive-field table (retinotopic_v1).

For every MaleCNS LPLC2 and LC4 cell the table lists the optic columns of its input synapses in
its own lobula and lobula plate, with the synapse count and the viewing direction of each
column (game/M3_4_RETINOTOPIC_DRIVE_RESEARCH.md, section 2; design section 2.2).

Sources, all public, fetched at build time:
- MaleCNS v1.0 synapse annotations (`optic_column` = hex1 * 100 + hex2), as in
  tools/m3_4_receptive_fields.py;
- the right-eye micro-CT eye map of Zhao et al. 2025 (https://github.com/reiserlab/eyemap_T4,
  fly 20240701), matched to MaleCNS columns by (h, v) offset from the eye centre [18, 19]; the
  left eye is its mirror image.

The table is built locally, like data/brain.npz, and is not committed: the eye-map repository is
GPL-3.0. Its content digest (game.perception.fields_digest) goes into encoder.retinotopic.
fields_sha256, and the encoder refuses any other table. Directions are copied from the eye map
without arithmetic other than sign changes, so a rebuild reproduces the digest exactly.

Extra dependencies, not in requirements.txt: `pip install mmh3 rdata`.

    git clone --depth 1 https://github.com/reiserlab/eyemap_T4 ../eyemap_T4
    python tools/build_receptive_fields.py --eyemap ../eyemap_T4
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.perception import LOOM_TYPES, RETINOTOPIC_FIELD_KEYS, THREAT_TYPES, fields_digest  # noqa: E402
import tools.m3_4_receptive_fields as RF  # noqa: E402

OUT = ROOT / 'data/receptive_fields_v1.npz'
TYPES = tuple(LOOM_TYPES + THREAT_TYPES)
EYE_MAP = 'Zhao et al. 2025, reiserlab/eyemap_T4 data/microCT/20240701 (right eye; left mirrored)'
SYNAPSES = RF.BUCKET + RF.LAYERS['synapses']


def build(eyemap_dir):
    eye = RF.EyeMap(eyemap_dir)
    ids, types, sides = RF.brain_arrays()
    syn = RF.AnnotationLayer('synapses')
    roi = syn.enum('primary_roi')
    cells = [int(i) for i in np.flatnonzero(np.isin(types, TYPES))]
    with ThreadPoolExecutor(8) as pool:
        records = list(pool.map(lambda i: syn.related('body_post', int(ids[i])), cells))
    codes, counts, directions, offsets = [], [], [], [0]
    for i, rec in zip(cells, records):
        side = str(sides[i])
        own = [roi[name] for name in RF.OWN_LOBE_ROIS[side]]
        m = np.isin(rec['primary_roi'], own) & (rec['optic_column'] > 0)
        c, n = np.unique(rec['optic_column'][m].astype(np.int32), return_counts=True)
        if not len(c):
            raise SystemExit('cell %d (body %d) has no column-assigned input synapses' % (i, ids[i]))
        codes.append(c)
        counts.append(n.astype(np.int32))
        directions.append(np.array([eye.column(int(code), side)[0] for code in c], np.float64))
        offsets.append(offsets[-1] + len(c))
    fields = {
        'cell_index': np.array(cells, np.int64),
        'cell_body': ids[cells].astype(np.int64),
        'cell_type': types[cells].astype('<U8'),
        'cell_side': sides[cells].astype('<U1'),
        'column_offsets': np.array(offsets, np.int64),
        'column_code': np.concatenate(codes).astype(np.int32),
        'column_count': np.concatenate(counts).astype(np.int32),
        'column_direction': np.concatenate(directions).astype(np.float64),
    }
    assert tuple(sorted(fields)) == RETINOTOPIC_FIELD_KEYS
    return fields


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--eyemap', required=True, help='path to a clone of reiserlab/eyemap_T4')
    parser.add_argument('--out', default=str(OUT))
    args = parser.parse_args()
    fields = build(args.eyemap)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, **fields)
    print('wrote %s: %d cells, %d columns' % (out, len(fields['cell_index']), len(fields['column_code'])))
    print('fields_sha256', fields_digest(fields))


if __name__ == '__main__':
    main()
