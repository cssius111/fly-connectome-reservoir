"""M3.4 research: LPLC2 and LC4 receptive fields from MaleCNS synapses (read-only).

Exploratory. No runtime file changes. game/M3_4_RETINOTOPIC_DRIVE_RESEARCH.md reports the
results. Outputs go to artifacts/m3_4/ (git-ignored).

Data, all public and fetched at run time:
- MaleCNS v1.0 synapse annotations (gs://flyem-male-cns/v1.0/male-cns-v1.0-synapses-precomputed),
  read through their by_rel_body_post index. Each synapse carries `optic_column` = hex1 * 100 + hex2;
- MaleCNS v1.0 optic-lobe column pins (gs://flyem-male-cns/v1.0/malecns-v1.0-optic-lobe-column-pins);
- the right-eye micro-CT eye map of Zhao et al. 2025 (fly 20240701 in
  https://github.com/reiserlab/eyemap_T4, data/microCT/). Clone it and pass its path with --eyemap.
  The repository is GPL-3.0: this tool reads its data files and copies none of its code.

Extra dependencies, not in requirements.txt: `pip install mmh3 rdata scipy`.

Subcommands:
- orientation: the anatomical direction of the hex axes in ME, LO and LOP, and a check of the
  `optic_column` encoding against the column pins;
- fields: the receptive field of every LPLC2 and LC4 cell (artifacts/m3_4/fields.json);
- gradients: LPLC2/LC4 -> DNp01, DNp02, DNp11, DNp04 weights against receptive-field position;
- reach: the DN input weight a disk reaches under coverage-weighted drive;
- simulate: coverage-weighted drive into the frozen network, seeds 920001-920012;
- explore: the same drive with an LPLC2 edge-speed requirement on the calibration stimulus,
  decided by the M3.3 doublet rule, seeds 930001-930024;
- sides: identical drive to the left or right encoder cells, seeds 920101-920124;
- mirror: the Retina streams of the N4B6 trajectories C1 and C2.

    git clone --depth 1 https://github.com/reiserlab/eyemap_T4 ../eyemap_T4
    python tools/m3_4_receptive_fields.py orientation
    python tools/m3_4_receptive_fields.py fields --eyemap ../eyemap_T4
    python tools/m3_4_receptive_fields.py gradients
    python tools/m3_4_receptive_fields.py reach --eyemap ../eyemap_T4
    python tools/m3_4_receptive_fields.py simulate --eyemap ../eyemap_T4 --scale 0.3 1.0 3.0
    python tools/m3_4_receptive_fields.py explore --eyemap ../eyemap_T4 --scale 1 2 3 5 8 12 20 30
    python tools/m3_4_receptive_fields.py explore --eyemap ../eyemap_T4 --scale 45 70 100 150 --edge-speed 10
    python tools/m3_4_receptive_fields.py explore --eyemap ../eyemap_T4 --edge-profile gaussian \
        --scale 5 10 20 40 80 160 320 --edge-speed 10
    python tools/m3_4_receptive_fields.py sides
    python tools/m3_4_receptive_fields.py mirror
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import urllib.request
import warnings

import numpy as np

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / 'artifacts/m3_4'
CACHE = OUT / 'cache'
BUCKET = 'https://storage.googleapis.com/flyem-male-cns/v1.0/'
LAYERS = {'synapses': 'male-cns-v1.0-synapses-precomputed',
          'pins': 'malecns-v1.0-optic-lobe-column-pins'}
TYPES = ('LPLC2', 'LC4')
DNS = ('DNp01', 'DNp02', 'DNp11', 'DNp04')
OWN_LOBE_ROIS = {'R': ('LO(R)', 'LOP(R)'), 'L': ('LO(L)', 'LOP(L)')}
CENTRE_HEX = (18, 19)               # hex1, hex2 of the eye centre (reiserlab convention)
SOFT_EDGE_DEG = 2.5                 # half the ~5 deg inter-ommatidial angle
ACCEPTANCE_FWHM_DEG = 7.70           # light-adapted R1-R6 acceptance angle (Juusola et al. 2017)
ACCEPTANCE_SIGMA_DEG = ACCEPTANCE_FWHM_DEG / (2 * math.sqrt(2 * math.log(2)))
SIMULATE_SEEDS = tuple(range(920001, 920013))
SIDES_SEEDS = tuple(range(920101, 920125))
EXPLORE_SEEDS = tuple(range(930001, 930025))
ACHE_POSITION_DEG = (50.0, 11.0)     # Ache et al. 2019 electrophysiology stimulus (az, el)
ALIGN = {'float32': 4, 'uint32': 4, 'int32': 4, 'uint16': 2, 'int16': 2, 'uint8': 1, 'int8': 1}


# ------------------------------------------------------- neuroglancer annotation shards ---
def http_get(url, start=None, end=None):
    request = urllib.request.Request(url)
    if start is not None:
        request.add_header('Range', 'bytes=%d-%d' % (start, end - 1))
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except OSError:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


class AnnotationLayer:
    """Reader for a neuroglancer precomputed annotation layer with uint64 sharded indices."""

    def __init__(self, name):
        self.base = BUCKET + LAYERS[name]
        info_path = CACHE / name / 'info'
        if not info_path.exists():
            info_path.parent.mkdir(parents=True, exist_ok=True)
            info_path.write_bytes(http_get(self.base + '/info'))
        self.info = json.loads(info_path.read_text(encoding='utf-8'))
        self.name = name
        props = self.info['properties']
        geometry = {'line': 6, 'point': 3}[self.info['annotation_type']]
        order = sorted(range(len(props)), key=lambda i: -ALIGN[props[i]['type']])
        fields = [('geom', '<f4', (geometry,))] + [
            (props[i]['id'], '<' + np.dtype(props[i]['type']).str[1:]) for i in order]
        size = 4 * geometry + sum(ALIGN[props[i]['type']] for i in order)
        if size % 4:
            fields.append(('_pad', 'V%d' % (4 - size % 4)))
        self.dtype = np.dtype(fields)

    def enum(self, prop):
        p = next(p for p in self.info['properties'] if p['id'] == prop)
        return dict(zip(p['enum_labels'], p['enum_values']))

    def _chunk(self, key, sharding, chunk_id):
        import mmh3
        mb, sb = sharding['minishard_bits'], sharding['shard_bits']
        h = mmh3.hash64(struct.pack('<Q', chunk_id >> sharding['preshift_bits']), 0, False, False)[0]
        minishard, shard = h & ((1 << mb) - 1), (h >> mb) & ((1 << sb) - 1)
        url = '%s/%s/%s.shard' % (self.base, key, '%0*x' % ((sb + 3) // 4, shard) if sb else '0')
        header = 16 << mb
        start, end = struct.unpack('<QQ', http_get(url, 16 * minishard, 16 * minishard + 16))
        if start == end:
            return None
        index = np.frombuffer(gzip.decompress(http_get(url, header + start, header + end)),
                              '<u8').reshape(3, -1)
        ids = np.cumsum(index[0])
        hit = np.flatnonzero(ids == np.uint64(chunk_id))
        if not len(hit):
            return None
        offsets = np.cumsum(index[1] + np.concatenate(([np.uint64(0)], index[2][:-1])))
        i = int(hit[0])
        data = http_get(url, header + int(offsets[i]), header + int(offsets[i]) + int(index[2][i]))
        return gzip.decompress(data) if sharding.get('data_encoding') == 'gzip' else data

    def _decode(self, blob):
        n = struct.unpack('<Q', blob[:8])[0]
        return np.frombuffer(blob, self.dtype, n, 8)

    def _cached(self, path, fetch):
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(fetch() or struct.pack('<Q', 0))
        return self._decode(path.read_bytes())

    def related(self, relationship, body):
        rel = next(r for r in self.info['relationships'] if r['id'] == relationship)
        return self._cached(CACHE / self.name / rel['key'] / ('%d.bin' % body),
                            lambda: self._chunk(rel['key'], rel['sharding'], body))

    def all_annotations(self):
        spatial = self.info['spatial'][0]
        if spatial['grid_shape'] != [1, 1, 1]:
            raise SystemExit('expected a single spatial chunk at level 0')
        return self._cached(CACHE / self.name / (spatial['key'] + '.bin'),
                            lambda: self._chunk(spatial['key'], spatial['sharding'], 0))


# ---------------------------------------------------------------------------- helpers ---
def brain_arrays():
    b = np.load(ROOT / 'data/brain.npz')
    return b['ids'], b['cell_type'], b['side']


def weights():
    import scipy.sparse as sp
    w = np.load(ROOT / 'data/weights.npz')
    return sp.csr_matrix((w['data'], w['indices'], w['indptr']), shape=tuple(w['shape']))


def room_config():
    from game.session import load_config
    return load_config(ROOT / 'game_room_config.json')


def encoder_cells():
    """The balanced LPLC2/LC4 subsets the ROOM encoder drives, from the runtime's own code."""
    from game.fly import build_brain
    from game.perception import RetinalEncoder
    config = room_config()
    brain = build_brain(config, ROOT, warmup=False)
    encoder = RetinalEncoder(brain, config)
    cells = {'LPLC2': encoder._fd.cells['loom'], 'LC4': encoder._fd.cells['threat']}
    return brain, encoder, cells


def hex_hv(hex1, hex2):
    """(h, v) lattice offsets from the eye centre: +h anterior on the eye, +v dorsal."""
    q, p = hex1 - CENTRE_HEX[0], hex2 - CENTRE_HEX[1]
    return q - p, q + p


def unit(az_deg, el_deg):
    a, e = math.radians(az_deg), math.radians(el_deg)
    return np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])


def az_el(d):
    return (math.degrees(math.atan2(d[1], d[0])),
            math.degrees(math.asin(max(-1.0, min(1.0, d[2])))))


class EyeMap:
    """Viewing direction of each MaleCNS column, from the Zhao et al. 2025 right-eye micro-CT.

    Ommatidia and columns are matched by their (h, v) offset from the eye centre, as Zhao et al.
    matched their EM columns to micro-CT ommatidia. Directions are in the head frame +x forward,
    +y right, +z up; the left eye is the mirror image of the right-eye map.
    """

    def __init__(self, eyemap_dir):
        import rdata
        folder = Path(eyemap_dir) / 'data' / 'microCT'
        if not (folder / '20240701.RData').exists():
            raise SystemExit('no micro-CT data under %s; clone https://github.com/reiserlab/eyemap_T4 '
                             'and pass it with --eyemap' % folder)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            fly = rdata.read_rda(str(folder / '20240701.RData'))
            lattice = rdata.read_rda(str(folder / '20240701_nb.RData'))
        left = np.asarray(fly['ind_left_lens'], bool)
        # Rows of ucl_rot_sm follow the cone index; i_match orders them by lens. Frame: +x
        # forward, +y left, +z up (vf, vleft, vn).
        directions = np.asarray(fly['ucl_rot_sm'])[np.argsort(np.asarray(fly['i_match']))][~left]
        hexes = np.asarray(lattice['ind_xy_right'])           # lens index (1-based), p, q
        p, q = hexes[:, 1].astype(int), hexes[:, 2].astype(int)
        d = directions[hexes[:, 0].astype(int) - 1]
        self.keys = np.c_[q - p, p + q]                       # +h anterior, +v dorsal
        self.directions = np.c_[d[:, 0], -d[:, 1], d[:, 2]]   # to +y right
        self.neighbour_deg = np.degrees(np.nanmedian(np.asarray(lattice['nb_dist_ucl_right'])[:, 1:]))
        self._memo = {}

    def column(self, code, side):
        """(unit direction, exact lattice match) of the MaleCNS column hex1 * 100 + hex2."""
        key = (code, side)
        if key not in self._memo:
            h, v = hex_hv(code // 100, code % 100)
            k = int(np.argmin(3 * (self.keys[:, 0] - h) ** 2 + (self.keys[:, 1] - v) ** 2))
            d = self.directions[k].copy()
            if side == 'L':
                d[1] = -d[1]
            self._memo[key] = (d, bool((self.keys[k] == (h, v)).all()))
        return self._memo[key]


def load_fields():
    path = OUT / 'fields.json'
    if not path.exists():
        raise SystemExit('run python tools/m3_4_receptive_fields.py fields --eyemap DIR first')
    return json.loads(path.read_text(encoding='utf-8'))


def spearman(x, y):
    from scipy.stats import spearmanr
    r = spearmanr(x, y)
    return float(r.statistic), float(r.pvalue)


# ------------------------------------------------------------------------ subcommands ---
def orientation(args):
    from scipy.spatial import cKDTree
    pins = AnnotationLayer('pins').all_annotations()
    rois = AnnotationLayer('pins').enum('roi')
    print('Physical direction of one hex step (EM voxels; +x = fly\'s left, +y = ventral, '
          '+z = posterior):')
    for name in ('ME(R)', 'LO(R)', 'LOP(R)', 'ME(L)', 'LO(L)', 'LOP(L)'):
        m = pins['roi'] == rois[name]
        mid = (pins['geom'][m][:, :3] + pins['geom'][m][:, 3:]) / 2
        h, v = hex_hv(pins['hex1'][m].astype(float), pins['hex2'][m].astype(float))
        coef = np.linalg.lstsq(np.c_[h, v, np.ones_like(h)], mid, rcond=None)[0]
        print('  %-7s columns %3d | +h %s | +v %s' % (
            name, len(set(zip(pins['hex1'][m], pins['hex2'][m]))), coef[0].round(0), coef[1].round(0)))
    ids, types, sides = brain_arrays()
    body = int(ids[np.flatnonzero((types == 'LPLC2') & (sides == 'R'))[0]])
    syn = AnnotationLayer('synapses')
    rec = syn.related('body_post', body)
    labels = syn.enum('primary_roi')
    print('optic_column against the nearest column pin, LPLC2 body %d:' % body)
    for name in ('LO(R)', 'LOP(R)'):
        pm = pins['roi'] == rois[name]
        tree = cKDTree((pins['geom'][pm][:, :3] + pins['geom'][pm][:, 3:]) / 2)
        m = (rec['primary_roi'] == labels[name]) & (rec['optic_column'] > 0)
        _, k = tree.query(rec['geom'][m][:, 3:])
        near = pins['hex1'][pm][k].astype(int) * 100 + pins['hex2'][pm][k]
        code = rec['optic_column'][m].astype(int)
        close = (abs(near // 100 - code // 100) <= 1) & (abs(near % 100 - code % 100) <= 1)
        print('  %-7s synapses %4d | exact %.3f | within one column %.3f' % (
            name, m.sum(), np.mean(near == code), np.mean(close)))


def fields(args):
    eye = EyeMap(args.eyemap)
    ids, types, sides = brain_arrays()
    syn = AnnotationLayer('synapses')
    labels = syn.enum('primary_roi')
    rows = [(i, int(ids[i]), str(sides[i]), str(types[i]))
            for i in np.flatnonzero(np.isin(types, TYPES))]
    with ThreadPoolExecutor(8) as pool:
        records = list(pool.map(lambda r: syn.related('body_post', r[1]), rows))
    out = {t: [] for t in TYPES}
    for (index, body, side, cell_type), rec in zip(rows, records):
        own = [labels[name] for name in OWN_LOBE_ROIS[side]]
        m = np.isin(rec['primary_roi'], own) & (rec['optic_column'] > 0)
        codes, counts = np.unique(rec['optic_column'][m].astype(int), return_counts=True)
        if not len(codes):
            continue
        dirs = np.array([eye.column(c, side)[0] for c in codes])
        w = counts / counts.sum()
        centre = (dirs * w[:, None]).sum(0)
        centre /= np.linalg.norm(centre)
        ang = np.degrees(np.arccos(np.clip(dirs @ centre, -1, 1)))
        order = np.argsort(ang)
        cum = np.cumsum(w[order])
        radius = {'r%d' % k: float(ang[order][np.searchsorted(cum, k / 100)]) for k in (50, 80, 95)}
        az, el = az_el(centre)
        out[cell_type].append({
            'index': int(index), 'body': body, 'side': side, 'input_synapses': int(len(rec)),
            'column_synapses': int(counts.sum()), 'columns': int(len(codes)),
            'exact_match': float(np.mean([eye.column(c, side)[1] for c in codes])),
            'az_deg': az, 'el_deg': el, **radius,
            'column_codes': codes.tolist(), 'column_counts': counts.tolist()})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'fields.json').write_text(json.dumps(out) + '\n', encoding='utf-8')
    print('micro-CT eye: %d ommatidia, median neighbour angle %.2f deg'
          % (len(eye.keys), eye.neighbour_deg))
    for t, cells in out.items():
        a = {k: np.array([c[k] for c in cells]) for k in cells[0]
             if not isinstance(cells[0][k], list)}
        print('%s: %d cells (L %d, R %d); median column synapses %d, columns %d; exact lattice '
              'match %.3f' % (t, len(cells), (a['side'] == 'L').sum(), (a['side'] == 'R').sum(),
                              np.median(a['column_synapses']), np.median(a['columns']),
                              a['exact_match'].mean()))
        for k in ('r50', 'r80', 'r95'):
            print('  %s median %.1f deg (IQR %.1f-%.1f)' % (k, np.median(a[k]),
                                                           *np.percentile(a[k], [25, 75])))
        for s in 'LR':
            m = a['side'] == s
            print('  side %s centres: az %.0f to %.0f, el %.0f to %.0f' % (
                s, a['az_deg'][m].min(), a['az_deg'][m].max(), a['el_deg'][m].min(),
                a['el_deg'][m].max()))


def gradients(args):
    _, types, sides = brain_arrays()
    W = weights()
    data = load_fields()
    _, _, used = encoder_cells()
    for t in TYPES:
        cells = data[t]
        index = np.array([c['index'] for c in cells])
        absaz = np.abs([c['az_deg'] for c in cells])
        el = np.array([c['el_deg'] for c in cells])
        side = np.array([c['side'] for c in cells])
        print('%s (Spearman over ipsilateral cells; weights are per-postsynaptic normalised):' % t)
        for dn in DNS:
            for s in 'LR':
                row = W[int(np.flatnonzero((types == dn) & (sides == s))[0])].toarray().ravel()
                ipsi = side == s
                w = row[index]
                if not w[ipsi].any():
                    print('  %s(%s) ipsilateral weight 0' % (dn, s))
                    continue
                ra, pa = spearman(absaz[ipsi], w[ipsi])
                re, pe = spearman(el[ipsi], w[ipsi])
                print('  %s(%s) ipsilateral %.3f, contralateral %.3f | |az| rho %+.2f (p %.1e) | '
                      'el rho %+.2f (p %.1e)' % (dn, s, w[ipsi].sum(), w[~ipsi].sum(), ra, pa, re, pe))
        for s in 'LR':
            chosen = np.isin(index, used[t][s])
            dn = int(np.flatnonzero((types == 'DNp01') & (sides == s))[0])
            print('  encoder %s: %d cells, front (<60) %d, lateral %d, back (>=110) %d; ventral (<0) '
                  '%d, middle %d, dorsal (>=40) %d; weight to DNp01 %.3f (all %s cells %.3f)' % (
                      s, chosen.sum(), (chosen & (absaz < 60)).sum(),
                      (chosen & (absaz >= 60) & (absaz < 110)).sum(), (chosen & (absaz >= 110)).sum(),
                      (chosen & (el < 0)).sum(), (chosen & (el >= 0) & (el < 40)).sum(),
                      (chosen & (el >= 40)).sum(), W[dn, used[t][s]].sum(), s,
                      W[dn, index[side == s]].sum()))
    print('Two-hop LPLC2 -> DNp01 weights of the driven subsets:')
    for s in 'LR':
        dn = int(np.flatnonzero((types == 'DNp01') & (sides == s))[0])
        direct = W[dn].toarray().ravel()
        two = direct * np.asarray(W[:, used['LPLC2'][s]].sum(axis=1)).ravel()
        print('  %s: direct %.3f, two-hop %.4f' % (s, direct[used['LPLC2'][s]].sum(), two.sum()))


class Coverage:
    """Fraction of each driven cell's column-weighted receptive field inside a disk.

    profile 'logistic': a logistic edge of SOFT_EDGE_DEG (the research note's sections 5-6);
    profile 'gaussian': each column sees the disk through a Gaussian acceptance function of
    ACCEPTANCE_FWHM_DEG half-width, so its share is the normal CDF of the edge distance.
    """

    def __init__(self, eye, used, profile='logistic'):
        self.profile = profile
        data = load_fields()
        self.cells = {}
        for t in TYPES:
            chosen = set(np.concatenate([used[t]['L'], used[t]['R']]).tolist())
            self.cells[t] = [
                (c['index'], c['side'],
                 np.array([eye.column(code, c['side'])[0] for code in c['column_codes']]),
                 np.array(c['column_counts'], float) / sum(c['column_counts']))
                for c in data[t] if c['index'] in chosen]

    def __call__(self, cell_type, centre, theta_deg):
        out = []
        for index, side, dirs, w in self.cells[cell_type]:
            ang = np.degrees(np.arccos(np.clip(dirs @ centre, -1, 1)))
            if self.profile == 'gaussian':
                from scipy.special import ndtr
                share = ndtr((theta_deg / 2 - ang) / ACCEPTANCE_SIGMA_DEG)
            else:
                share = 1 / (1 + np.exp((ang - theta_deg / 2) / SOFT_EDGE_DEG))
            out.append((index, side, float((w * share).sum())))
        return out


def reach(args):
    eye = EyeMap(args.eyemap)
    _, types, sides = brain_arrays()
    W = weights()
    _, _, used = encoder_cells()
    cover = Coverage(eye, used)
    dn = {'%s_%s' % (d, s): int(np.flatnonzero((types == d) & (sides == s))[0])
          for d in DNS for s in 'LR'}

    def total(cell_type, target, az, el, theta):
        return sum(c * W[dn[target], i] for i, _, c in cover(cell_type, unit(az, el), theta))

    azimuths = (10, 40, 70, 100, 130)
    print('DNp01 weight reached by a 40 deg disk; right eye at +az, left eye mirrored:')
    for t in TYPES:
        print(' ', t, '(az %s)' % ', '.join(map(str, azimuths)))
        for el in (60, 30, 0, -30):
            r = [total(t, 'DNp01_R', az, el, 40) for az in azimuths]
            l = [total(t, 'DNp01_L', -az, el, 40) for az in azimuths]
            print('    el %+3d  R %s | L %s' % (el, ' '.join('%.4f' % x for x in r),
                                               ' '.join('%.4f' % x for x in l)))
    print('LPLC2 + LC4 -> DNp01 against disk size at az 70, el 0 (R) and az -70 (L):')
    for theta in (10, 20, 30, 40, 60, 90):
        print('  theta %3d  R %.4f  L %.4f' % (
            theta, sum(total(t, 'DNp01_R', 70, 0, theta) for t in TYPES),
            sum(total(t, 'DNp01_L', -70, 0, theta) for t in TYPES)))
    print('LC4 -> DNp02 and DNp11, 40 deg disk at el 0, right eye:')
    for az in (10, 40, 70, 100, 130, 150):
        a, p = total('LC4', 'DNp02_R', az, 0, 40), total('LC4', 'DNp11_R', az, 0, 40)
        print('  az %3d  DNp02 %.4f  DNp11 %.4f  DNp11 share %.2f' % (az, a, p, p / (a + p)))


def ache_features(theta, theta_dot):
    """The M3.2 Ache et al. 2019 LPLC2 (size) and LC4 (angular velocity) terms in mV."""
    from game.perception import ACHE2019 as a
    r = math.log(math.degrees(theta) / a['lplc2_center_deg'])
    lplc2 = a['weight_lplc2'] * a['lplc2_peak_mv'] * math.exp(-r * r / (2 * a['lplc2_log_width'] ** 2))
    return {'LPLC2': lplc2, 'LC4': a['weight_lc4'] * a['lc4_mv_per_deg_s'] * math.degrees(theta_dot)}


def simulate(args):
    """Coverage-weighted Ache et al. 2019 drive: scale * feature (mV) * coverage, capped at 0.8 V."""
    eye = EyeMap(args.eyemap)
    brain, encoder, used = encoder_cells()
    cover = Coverage(eye, used)
    _, types, sides = brain_arrays()
    dn = {'%s_%s' % (d, s): int(np.flatnonzero((types == d) & (sides == s))[0])
          for d in DNS for s in 'LR'}
    lv, dt, cap = 0.04, float(room_config()['sim']['tick_seconds']), 0.8
    t0 = -lv / math.tan(math.radians(5.0))
    t1 = -lv / math.tan(math.radians(45.0))
    pre, stim, post = 30, int(math.ceil((t1 - t0) / dt)), 10
    conditions = (('front', 20, 0), ('lateral', 70, 0), ('back', 120, 0), ('dorsal', 70, 50),
                  ('ventral', 70, -40), ('lateral-left', -70, 0))

    results = {}
    for scale in args.scale:
        for name, az, el in conditions:
            centre, counts = unit(az, el), {k: [] for k in dn}
            for seed in SIMULATE_SEEDS:
                brain.reset(seed)
                previous, spikes = math.radians(10.0), dict.fromkeys(dn, 0)
                for k in range(pre + stim + post):
                    inject = []
                    if pre <= k < pre + stim:
                        theta = min(2 * math.atan(lv / -(t0 + (k - pre + 1) * dt)), math.radians(90.0))
                        theta_dot, previous = (theta - previous) / dt, theta
                        if theta_dot > 0:
                            for t, mv in ache_features(theta, theta_dot).items():
                                for i, _, c in cover(t, centre, math.degrees(theta)):
                                    if scale * mv * c > 1e-4:
                                        inject.append((np.array([i]), min(cap, scale * mv * c)))
                    fired = brain.step(inject=inject)
                    if k >= pre:
                        for key, i in dn.items():
                            spikes[key] += int(i in fired)
                for key in dn:
                    counts[key].append(spikes[key])
            results['%.2f %s' % (scale, name)] = {k: float(np.mean(v)) for k, v in counts.items()}
            print('scale %.2f %-12s az %4d el %4d | %s' % (scale, name, az, el, ' '.join(
                '%s %.2f' % (k, v) for k, v in results['%.2f %s' % (scale, name)].items())), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'simulate.json').write_text(json.dumps(results, indent=1) + '\n', encoding='utf-8')


def explore(args):
    """Coverage-weighted drive with an LPLC2 edge-speed requirement, decided by the M3.3 doublet rule.

    The M3.2/M3.3 calibration stimulus (10 -> 90 deg, l/v 10-80 ms) at the Ache et al. 2019
    electrophysiology position (azimuth 50 deg, elevation 11 deg). LPLC2 cells are driven only
    while the disk edge expands at >= the given speed (deg/s; 0 = any expansion). The first
    same-side DNp01 doublet (<= 2 samples apart) inside the calibration window is the escape.
    Seeds 930001-930024.
    """
    import tools.m3_2_ache_targets as T
    import tools.m3_2_escape_roles as R
    eye = EyeMap(args.eyemap)
    brain, _, used = encoder_cells()
    cover = Coverage(eye, used, args.edge_profile)
    escape = {s: int(brain.groups['escape_' + s][0]) for s in 'LR'}
    dt, cap = float(room_config()['sim']['tick_seconds']), 0.8
    targets = {r['lv_ms']: r['peak_time_ms'] / 1000.0 for r in T.targets(T.CALIBRATION_LV_MS)}
    centre = unit(*ACHE_POSITION_DEG)
    stimuli = {}
    for lv_ms in T.CALIBRATION_LV_MS:
        retinas, pre, t0, thetas, last = R.looming(lv_ms / 1000.0, dt, 10.0, 90.0,
                                                   targets[lv_ms] + R.WINDOW_AFTER_TARGET_S)
        ticks = []
        for r in retinas:
            if r.theta_dot > 0:
                ticks.append((math.degrees(r.theta_dot) / 2, ache_features(r.theta, r.theta_dot),
                              {t: cover(t, centre, math.degrees(r.theta)) for t in TYPES}))
            else:
                ticks.append(None)
        stimuli[lv_ms] = (ticks, pre, t0, last)
    results = {}
    for edge_speed in args.edge_speed:
        for scale in args.scale:
            row = {}
            for lv_ms, (ticks, pre, t0, last) in stimuli.items():
                drives = []
                for tick in ticks:
                    inject = []
                    if tick is not None:
                        speed, mv, cov = tick
                        for t in TYPES:
                            if t == 'LPLC2' and speed < edge_speed:
                                continue
                            inject += [(np.array([i]), min(cap, scale * mv[t] * c))
                                       for i, _, c in cov[t] if scale * mv[t] * c > 1e-4]
                    drives.append(inject)
                times = []
                for seed in EXPLORE_SEEDS:
                    brain.reset(seed)
                    previous, first = {'L': None, 'R': None}, None
                    for k, inject in enumerate(drives):
                        fired = brain.step(inject=inject)
                        for s in 'LR':
                            if escape[s] in fired:
                                if previous[s] is not None and k - previous[s] <= 2 and pre <= k <= last:
                                    first = k
                                previous[s] = k
                        if first is not None:
                            break
                    times.append(None if first is None else ((first - pre + 1) * dt - t0) * 1000.0)
                hit = [x for x in times if x is not None]
                row[lv_ms] = {'fraction': len(hit) / len(times),
                              'median_t_ms': float(np.median(hit)) if hit else None,
                              'target_ms': targets[lv_ms] * 1000.0}
            results['edge %.0f scale %.2f' % (edge_speed, scale)] = row
            print('edge >= %4.1f deg/s, scale %5.2f | %s' % (edge_speed, scale, ' | '.join(
                '%d ms %.2f %s/%+.0f' % (lv, r['fraction'], '-' if r['median_t_ms'] is None
                                         else '%+.0f' % r['median_t_ms'], r['target_ms'])
                for lv, r in row.items())), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    name = 'explore_%s_%s.json' % (args.edge_profile, '_'.join('%g' % x for x in args.scale))
    (OUT / name).write_text(json.dumps(results, indent=1) + '\n', encoding='utf-8')


def sides_test(args):
    """Constant drive to one side's encoder cells for 0.5 s after 0.6 s at rest."""
    brain, encoder, used = encoder_cells()
    escape = {s: int(brain.groups['escape_' + s][0]) for s in 'LR'}
    results = {}
    for channel in ('LPLC2', 'LC4', 'both'):
        for amount in (0.04, 0.08, 0.12, 0.2, 0.3, 0.4, 0.55, 0.8):
            row = {}
            for s in 'LR':
                cells = [used[t][s] for t in TYPES if channel in (t, 'both')]
                spikes, doublets = [], []
                for seed in SIDES_SEEDS:
                    brain.reset(seed)
                    for _ in range(30):
                        brain.step()
                    times = [k for k in range(25)
                             if escape[s] in brain.step(inject=[(c, amount) for c in cells])]
                    spikes.append(len(times))
                    doublets.append(any(b - a <= 2 for a, b in zip(times, times[1:])))
                row[s] = {'spikes': float(np.mean(spikes)), 'doublet': float(np.mean(doublets))}
            results['%s %.2f' % (channel, amount)] = row
            print('%-5s %.2f V | L spikes %.2f doublet %.2f | R spikes %.2f doublet %.2f' % (
                channel, amount, row['L']['spikes'], row['L']['doublet'], row['R']['spikes'],
                row['R']['doublet']), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'sides.json').write_text(json.dumps(results, indent=1) + '\n', encoding='utf-8')


def mirror(args):
    from game.session import Session
    import tools.n4b6_controlled_approach as N
    P = N.P
    session = Session(room_config(), root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    series = {}
    for tid in ('C1_oblique_slow_right', 'C2_oblique_slow_left'):
        offsets, pointer, _ = N.pointer_path(tid)
        session.reset(P.SEEDS[0])
        N.place(session, offsets)
        rows = []
        for ox, oy in pointer:
            session.tick(pointer=(P.FLY_POSE[0] + ox, P.FLY_POSE[1] + oy), strike=False)
            r = session.last_retina
            rows.append((r.theta, r.theta_dot, r.azimuth))
        series[tid] = np.array(rows)
    session.close()
    right, left = series['C1_oblique_slow_right'], series['C2_oblique_slow_left']
    print('ticks %d; max |theta_C1 - theta_C2| %.6f deg; max |az_C1 + az_C2| %.6f' % (
        len(right), math.degrees(np.abs(right[:, 0] - left[:, 0]).max()),
        np.abs(right[:, 2] + left[:, 2]).max()))
    print('C1 after motion onset (tick, s after onset, theta deg, theta_dot rad/s):')
    for k in range(P.PRE_HOLD_TICKS + 260, len(right), 8):
        print('  %4d %5.2f %7.3f %+.4f' % (k, (k - P.PRE_HOLD_TICKS + 1) * N.DT,
                                          math.degrees(right[k, 0]), right[k, 1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('orientation', 'fields', 'gradients', 'reach', 'simulate',
                                         'explore', 'sides', 'mirror'))
    parser.add_argument('--eyemap', help='path to a clone of reiserlab/eyemap_T4')
    parser.add_argument('--scale', type=float, nargs='+', default=[0.3, 1.0, 3.0])
    parser.add_argument('--edge-speed', type=float, nargs='+', default=[10.0, 0.0],
                        help='explore: minimum LPLC2 edge speed in deg/s (0 = any expansion)')
    parser.add_argument('--edge-profile', choices=('logistic', 'gaussian'), default='logistic',
                        help='explore: disk edge seen by each column')
    args = parser.parse_args()
    if args.mode in ('fields', 'reach', 'simulate', 'explore') and not args.eyemap:
        parser.error('%s needs --eyemap' % args.mode)
    {'orientation': orientation, 'fields': fields, 'gradients': gradients, 'reach': reach,
     'simulate': simulate, 'explore': explore, 'sides': sides_test, 'mirror': mirror}[args.mode](args)


if __name__ == '__main__':
    main()
