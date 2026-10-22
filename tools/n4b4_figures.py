"""M1.8-N4B4 research: diagnostic figures for the free-flight escape review set.

Research only; reads artifacts/m1_8_n4b4/analysis.json and the replay files. Each event
figure shows, around one N4B1C no-player escape:

1. a top-down view: the parked paddle's footprint, the fly's factual path (escape applied)
   and the counterfactual path (escape withheld), 1 s before to 1.5 s after the escape;
2. Retina theta and theta_dot (offline only);
3. summed LC4/LPLC2 encoder drive (offline only);
4. DNp01 left / right traces as the policy saw them, with inferred spikes and the escape.

    python tools/n4b4_figures.py      # writes artifacts/m1_8_n4b4/figures/*.png
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'artifacts' / 'matplotlib'))
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_n4b4'
FIG = OUT / 'figures'
BLUE, ORANGE, AQUA = '#2a78d6', '#eb6834', '#1baf7a'     # validated categorical slots 1-3
INK, MUTED, GRID = '#0b0b0b', '#52514e', '#e4e3df'
PRE, POST = 50, 75


def style(ax):
    ax.grid(True, color=GRID, linewidth=0.6)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)


def event_figure(ev):
    name = '%s_seed%d' % (ev['source'], ev['seed'])
    fact = json.loads((OUT / (name + '.json')).read_text(encoding='utf-8'))
    farr = np.load(OUT / (name + '.npz'))
    cf = json.loads((OUT / ('%s_cf%d.json' % (name, ev['tick']))).read_text(encoding='utf-8'))
    rows = fact['rows']
    idx = {r['tick']: i for i, r in enumerate(rows)}
    i = idx[ev['tick']]
    lo, hi = max(0, i - PRE), min(len(rows), i + POST + 1)
    w = rows[lo:hi]
    t = np.array([(r['tick'] - ev['tick']) * 0.02 for r in w])
    cfi = {r['tick']: j for j, r in enumerate(cf['rows'])}[ev['tick']]
    cw = cf['rows'][cfi:cfi + POST + 1]

    fig = plt.figure(figsize=(11, 6.2), dpi=110)
    gs = fig.add_gridspec(3, 2, width_ratios=[1, 1.35], hspace=0.45, wspace=0.28)
    # 1. top-down
    ax = fig.add_subplot(gs[:, 0])
    px, py = rows[i]['paddle'][0], rows[i]['paddle'][1]
    ax.add_patch(plt.Circle((px, py), 144.0, facecolor='#f0efec', edgecolor=MUTED, linewidth=1.0))
    ax.add_patch(plt.Circle((px, py), 155.0, fill=False, edgecolor=MUTED, linestyle=':', linewidth=0.8))
    ax.text(px, py, 'parked paddle\n(320 units above)', ha='center', va='center', fontsize=7, color=MUTED)
    fx = [r['fly'][0] for r in w]
    fy = [r['fly'][1] for r in w]
    ax.plot(fx, fy, color=BLUE, linewidth=2, label='factual (escape applied)')
    ax.plot([r['fly'][0] for r in cw], [r['fly'][1] for r in cw], color=ORANGE, linewidth=2, linestyle='--',
            label='counterfactual (escape withheld)')
    ax.plot(rows[i]['fly'][0], rows[i]['fly'][1], marker='o', markersize=8, color=INK, linestyle='none',
            label='escape sample')
    ax.plot(fx[0], fy[0], marker='s', markersize=6, color=MUTED, linestyle='none', label='1 s before')
    ax.set_aspect('equal')
    allx = fx + [r['fly'][0] for r in cw] + [px - 160, px + 160]
    ally = fy + [r['fly'][1] for r in cw] + [py - 160, py + 160]
    pad = 40
    ax.set_xlim(min(allx) - pad, max(allx) + pad)
    ax.set_ylim(max(ally) + pad, min(ally) - pad)       # screen coordinates: y down
    ax.set_title('Top-down view (offline geometry)', fontsize=9, color=INK, loc='left')
    ax.legend(fontsize=7, loc='lower left', frameon=False)
    style(ax)
    # 2. theta / theta_dot
    a2 = fig.add_subplot(gs[0, 1])
    a2.plot(t, [r['theta_dot'] for r in w], color=BLUE, linewidth=2, label='theta_dot (rad/s)')
    a2.plot(t, [r['theta'] for r in w], color=ORANGE, linewidth=2, label='theta (rad)')
    a2.axvline(0, color=INK, linewidth=1)
    a2.set_title('Retina (offline only)', fontsize=9, color=INK, loc='left')
    a2.legend(fontsize=7, loc='upper left', frameon=False, ncol=2)
    style(a2)
    # 3. encoder drive
    a3 = fig.add_subplot(gs[1, 1], sharex=a2)
    st = list(farr['stepped_ticks'])
    k0 = st.index(lo)
    drv = farr['drive'][k0:k0 + len(w)].sum(1)
    sens = farr['sensory'][k0:k0 + len(w)]
    a3.plot(t, drv, color=BLUE, linewidth=2, label='summed LC4/LPLC2 drive')
    a3.axvline(0, color=INK, linewidth=1)
    peak_l = int((sens[:, 0] + sens[:, 2]).max())
    peak_r = int((sens[:, 1] + sens[:, 3]).max())
    a3.set_title('Encoder drive (offline only); peak volley L %d / R %d cells' % (peak_l, peak_r),
                 fontsize=9, color=INK, loc='left')
    style(a3)
    # 4. DNp01
    a4 = fig.add_subplot(gs[2, 1], sharex=a2)
    tl = np.array([r['dnp01_left'] for r in w])
    tr = np.array([r['dnp01_right'] for r in w])
    a4.plot(t, tl, color=BLUE, linewidth=2, label='DNp01 left')
    a4.plot(t, tr, color=ORANGE, linewidth=2, label='DNp01 right')
    a4.plot(t, tl + tr, color=MUTED, linewidth=1, linestyle=':', label='summed')
    decay = float(np.float32(np.exp(-0.2)))
    for tr_, col in ((tl, BLUE), (tr, ORANGE)):
        sp = [j for j in range(1, len(tr_)) if tr_[j] - decay * tr_[j - 1] >= 0.5]
        a4.plot(t[sp], tr_[sp], marker='o', markersize=8, color=col, linestyle='none',
                markeredgecolor='#fcfcfb', markeredgewidth=2)
    a4.axhline(2.10, color=MUTED, linewidth=0.8, linestyle='--')
    a4.text(t[-1], 2.12, 'FAST 2.10', fontsize=7, color=MUTED, ha='right', va='bottom')
    a4.axvline(0, color=INK, linewidth=1)
    a4.set_xlabel('time from escape (s)', fontsize=8, color=MUTED)
    a4.set_title('DNp01 traces (policy input); dots = inferred spikes', fontsize=9, color=INK, loc='left')
    a4.legend(fontsize=7, loc='upper left', frameon=False, ncol=3)
    style(a4)
    fig.suptitle('%s seed %d tick %d: %s escape; class %s (%s; %s)' % (
        ev['source'], ev['seed'], ev['tick'], ev['paths'], ev['class'], ev['neural_cause'],
        ev['counterfactual_outcome']), fontsize=10, color=INK, x=0.01, ha='left')
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / ('event_%s_%d_%d.png' % (ev['source'], ev['seed'], ev['tick']))
    fig.savefig(path, facecolor='#fcfcfb')
    plt.close(fig)
    return path


def summary_figure(events):
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=110)
    marks = {'A': ('o', BLUE, 'A collision-like approach'), 'B': ('s', ORANGE, 'B near pass'),
             'C': ('^', AQUA, 'C pathological')}
    for c, (m, col, lab) in marks.items():
        e = [x for x in events if x['class'] == c]
        if not e:
            continue
        ax.plot([x['counterfactual_min_horizontal_1_5s'] for x in e], [x['theta_dot'] for x in e],
                marker=m, markersize=9, linestyle='none', color=col, markeredgecolor='#fcfcfb',
                markeredgewidth=2, label='%s (%d)' % (lab, len(e)))
    ax.axvline(155, color=MUTED, linewidth=0.8, linestyle='--')
    ax.axvline(310, color=MUTED, linewidth=0.8, linestyle=':')
    ax.text(155, ax.get_ylim()[1], ' footprint', fontsize=7, color=MUTED, va='top')
    ax.text(310, ax.get_ylim()[1], ' 2 x footprint', fontsize=7, color=MUTED, va='top')
    ax.set_xlabel('closest horizontal distance within 1.5 s if the escape is withheld (units)', fontsize=8, color=MUTED)
    ax.set_ylabel('theta_dot at the escape (rad/s, offline)', fontsize=8, color=MUTED)
    ax.set_title('N4B1C no-player free-flight escapes (%d events)' % len(events), fontsize=10, color=INK, loc='left')
    ax.legend(fontsize=8, frameon=False, loc='upper right')
    style(ax)
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / 'summary_events.png'
    fig.tight_layout()
    fig.savefig(path, facecolor='#fcfcfb')
    plt.close(fig)
    return path


def main():
    a = json.loads((OUT / 'analysis.json').read_text(encoding='utf-8'))
    events = a['events']
    print(summary_figure(events))
    review = a.get('review_set') or [{'source': e['source'], 'seed': e['seed'], 'tick': e['tick']} for e in events]
    keys = {(r['source'], r['seed'], r['tick']) for r in review}
    for e in events:
        if (e['source'], e['seed'], e['tick']) in keys:
            print(event_figure(e))


if __name__ == '__main__':
    main()
