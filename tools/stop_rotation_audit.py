"""Read-only audit of the swatter stop-rotation transient in recorded human play.

Diagnostic only. It reads recorded ROOM sessions, writes nothing, and changes neither the frozen
M1.7.1 swatter nor any tilt geometry. It answers the open question of M1.8-N4B6
(game/M1_8_N4B6_CONTROLLED_SLOW_APPROACH.md section 4): how often real play
produces the stop-rotation transient, in which the hovering paddle swings its axis by about 90
degrees while it corrects an overshoot and so grows in apparent size at constant range
(0.35 rad/s of size-driven expansion in the orbit control, with an escape in 17 of 48 trials).

Timing. Every row stores the Retina projected before physics from the previous row's state, and
the fly and paddle state after physics (the manifest's time_alignment). The expansion first seen
in row t therefore comes from the geometry change between rows t-2 and t-1, and a sample counts
only when both of those rows are in the approach (hover) phase with a live, airborne fly.

For every such sample it measures the image expansion the policy saw, split into range-driven
and apparent-size-driven parts with the paddle half-size recovered from the recorded retina
angle. A *size-driven episode* is a run of samples whose size-driven expansion is at least
0.2 rad/s while the range-driven part stays below half of it.

* A *stop-rotation transient* is a size-driven episode during which the paddle axis (modulo 180
  degrees, because the tilt term uses |sin(bearing - axis)|) turns by at least 60 degrees,
  counted from 0.3 s before its first source row to its last one. An *axis flip* is any turn of
  at least 60 degrees within 0.3 s of hover.
* A *reversal spin* is a transient whose paddle turns by at least 120 degrees but ends within 30
  degrees of its starting axis. The approach controller steers the paddle towards the 360-degree
  heading of its velocity, so reversing the motion spins the paddle although its axis line ends
  where it was.

Escape attribution. An episode is evaluated only when no policy escape onset falls between 1 s
before it and 0.06 s after it; an escape onset 0.06-0.8 s after its first sample counts as a
possible response (0.06 s is just under the 0.08 s direct-strike latency of N1, and N4B6 saw
transient responses 0.44-0.64 s after the stop). The same rule is applied to baseline hover
samples taken every 0.5 s and at least 1 s from any size-driven episode, binned by horizontal
distance, and the excess over that baseline estimates how many escapes the transients add. The
baseline includes range-driven approaches, so the excess is conservative.

Only human play (mode 'play') is counted unless --all-modes is given; scripted 'evaluation'
recordings (for example tools/session_sanity.py) and repeated input streams are skipped. Totals
are reported separately for the accepted runtime (elevation-aware tilt with the N4B1C decoder,
config_version 17 and later) and for earlier runtimes.

Recordings of the M2.4-B blind test are refused until that test is unblinded
(game/M2_4_B_REOPENING.md section 4).

    python tools/stop_rotation_audit.py [--all-modes] [--list] SESSION_OR_SESSIONS_DIRECTORY [...]
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

FLIP_DEGREES = 60.0
FLIP_WINDOW_S = 0.3
REVERSAL_DEGREES = 120.0
REVERSAL_NET_DEGREES = 30.0
SIZE_RATE = 0.2           # rad/s of apparent-size expansion
RANGE_FRACTION = 0.5      # the range-driven part stays below this fraction of the size part
LATENCY_S = (0.06, 0.8)
PRIOR_ESCAPE_S = 1.0
BASELINE_STEP_S = 0.5
BASELINE_CLEAR_S = 1.0
DISTANCE_BINS = (200.0, 400.0, 600.0)   # horizontal units
NEAR_UNITS = 600.0
GROUPS = ('transients', 'reversal spins', 'size-driven, no swing', 'baseline hover')


def sessions(paths):
    for path in paths:
        path = path.resolve()
        if 'm2_4_b' in path.parts:
            raise SystemExit('refusing a path under m2_4_b: the blind-test recordings stay sealed')
        if (path / 'manifest.json').exists():
            yield path
        else:
            yield from sorted(p.parent for p in path.glob('*/manifest.json'))


def axis_delta(a, b):
    """Change of the paddle axis between two orientations, modulo pi, in (-pi/2, pi/2]."""
    d = (b - a) % math.pi
    return d - math.pi if d > math.pi/2 else d


def runtime(manifest):
    config = manifest.get('config') or {}
    tilt = config.get('swatter', {}).get('directional', {}).get('tilt_geometry')
    decoder = config.get('policy', {}).get('escape_decoder')
    return 'accepted' if tilt == 'elevation_aware_tilt_v1' and decoder else 'earlier'


def input_fingerprint(folder):
    """Hash of the recorded input stream without wall-clock times; human play never repeats it."""
    digest = hashlib.sha256()
    with (folder / 'inputs.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            op = json.loads(line)
            op.pop('wall_seconds', None)
            digest.update(json.dumps(op, sort_keys=True).encode())
    return digest.hexdigest()


def distance_bin(units):
    return sum(units >= edge for edge in DISTANCE_BINS)


def audit(folder, manifest):
    dt = manifest['tick_seconds']
    rows = []
    with (folder / 'ticks.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            r = json.loads(line)
            sw, fly = r['swatter'], r['fly']
            life = r.get('lifecycle') or {}
            rows.append({'episode': r['episode'], 'alive': fly['alive'], 'airborne': life.get('airborne', True),
                         'phase': sw.get('phase'), 'orientation': sw.get('orientation', 0.0),
                         'fx': fly['x'], 'fy': fly['y'], 'sx': sw['x'], 'sy': sw['y'], 'h': sw['height'],
                         'theta': r['retina']['theta'], 'escape': r['event_flags'].get('escape_onset', False)})
    n, window = len(rows), max(1, int(round(FLIP_WINDOW_S/dt)))
    lo, hi = int(round(LATENCY_S[0]/dt)), int(round(LATENCY_S[1]/dt))
    prior, step, clear = (int(round(s/dt)) for s in (PRIOR_ESCAPE_S, BASELINE_STEP_S, BASELINE_CLEAR_S))
    same = lambda i, j: 0 <= min(i, j) and max(i, j) < n and rows[i]['episode'] == rows[j]['episode']
    hover = lambda i: rows[i]['alive'] and rows[i]['airborne'] and rows[i]['phase'] == 'approach'
    sample = lambda t: same(t - 2, t) and hover(t - 2) and hover(t - 1)
    dist = lambda i: math.sqrt((rows[i]['fx']-rows[i]['sx'])**2 + (rows[i]['fy']-rows[i]['sy'])**2 + rows[i]['h']**2)
    horiz = lambda i: math.hypot(rows[i]['fx']-rows[i]['sx'], rows[i]['fy']-rows[i]['sy'])
    rotation = lambda first, last: sum(axis_delta(rows[j-1]['orientation'], rows[j]['orientation'])
                                       for j in range(first + 1, last + 1))

    def response(t):
        """None if an escape onset falls 1 s before to 0.06 s after t, else the delay of the
        first onset 0.06-0.8 s after t, or False."""
        if any(rows[j]['escape'] for j in range(t - prior, t + lo) if same(j, t)):
            return None
        j = next((j for j in range(t + lo, t + hi + 1) if same(t, j) and rows[j]['escape']), None)
        return False if j is None else (j - t)*dt

    flips, last_flip, hover_ticks = [], -10**9, 0
    size_rate, range_rate = [0.0]*n, [0.0]*n
    for t in range(n):
        if hover(t):
            hover_ticks += 1
            if same(t - window, t) and all(hover(j) for j in range(t - window, t + 1)):
                if math.degrees(abs(rotation(t - window, t))) >= FLIP_DEGREES and t - last_flip > window:
                    flips.append(t)
                    last_flip = t
        if sample(t):
            a, b = t - 2, t - 1
            ra, rb = dist(a), dist(b)
            ha, hb = ra*math.tan(rows[a+1]['theta']/2), rb*math.tan(rows[b+1]['theta']/2)
            range_rate[t] = (2*math.atan(ha/rb) - 2*math.atan(ha/ra))/dt
            size_rate[t] = (2*math.atan(hb/rb) - 2*math.atan(ha/rb))/dt
    driven = lambda t: sample(t) and size_rate[t] >= SIZE_RATE and abs(range_rate[t]) < RANGE_FRACTION*size_rate[t]

    episodes, t = [], 0
    while t < n:
        if driven(t):
            start = t
            while same(start, t + 1) and driven(t + 1):
                t += 1
            # Source rows of the episode are start-2 .. t-1; the swing is counted from 0.3 s
            # before them, and the reversal test looks 0.3 s past them.
            first, last = start - 2, t - 1
            while first > start - 2 - window and same(first - 1, start) and hover(first - 1):
                first -= 1
            after = last
            while after < last + window and same(start, after + 1) and hover(after + 1):
                after += 1
            swing = math.degrees(abs(rotation(first, last)))
            turned = math.degrees(abs(rotation(first, after)))
            net = math.degrees(abs(axis_delta(rows[first]['orientation'], rows[after]['orientation'])))
            transient = swing >= FLIP_DEGREES
            episodes.append({'tick': start, 'episode': rows[start]['episode'], 'ticks': t - start + 1,
                             'peak_size_rad_s': max(size_rate[start:t+1]), 'horizontal_units': horiz(start - 1),
                             'transient': transient, 'swing_degrees': swing, 'net_axis_degrees': net,
                             'reversal': transient and turned >= REVERSAL_DEGREES and net <= REVERSAL_NET_DEGREES,
                             'response': response(start)})
        t += 1

    near_episode = [False]*n
    for e in episodes:
        for j in range(max(0, e['tick'] - clear), min(n, e['tick'] + e['ticks'] + clear)):
            near_episode[j] = True
    groups = {g: [[0, 0] for _ in range(len(DISTANCE_BINS) + 1)] for g in GROUPS}

    def tally(group, t, outcome):
        if outcome is not None:
            cell = groups[group][distance_bin(horiz(t - 1))]
            cell[0] += 1
            cell[1] += outcome is not False

    for e in episodes:
        if e['transient']:
            tally('transients', e['tick'], e['response'])
            if e['reversal']:
                tally('reversal spins', e['tick'], e['response'])
        else:
            tally('size-driven, no swing', e['tick'], e['response'])
    for t in range(0, n, step):
        if sample(t) and not near_episode[t]:
            tally('baseline hover', t, response(t))
    return {'session': folder.name, 'config_version': manifest.get('config_version'), 'runtime': runtime(manifest),
            'hover_minutes': hover_ticks*dt/60, 'axis_flips': len(flips),
            'axis_flips_near': sum(horiz(f) < NEAR_UNITS for f in flips),
            'escape_onsets': sum(1 for r in rows if r['escape']), 'episodes': episodes, 'groups': groups}


def report(label, results):
    minutes = sum(r['hover_minutes'] for r in results)
    per_min = lambda count: count/minutes if minutes else float('nan')
    flips = sum(r['axis_flips'] for r in results)
    episodes = [e for r in results for e in r['episodes']]
    transients = [e for e in episodes if e['transient']]
    reversals = [e for e in transients if e['reversal']]
    print('\n%s: %d sessions | hover (approach phase, fly alive and airborne) %.1f min' % (label, len(results), minutes))
    if not results:
        return
    print('  axis flips %d (%.2f/min), near %d | escape onsets %d'
          % (flips, per_min(flips), sum(r['axis_flips_near'] for r in results), sum(r['escape_onsets'] for r in results)))
    print('  size-driven episodes %d | stop-rotation transients %d (%.2f/min), of which reversal spins %d (%.2f/min)'
          % (len(episodes), len(transients), per_min(len(transients)), len(reversals), per_min(len(reversals))))
    if transients:
        peaks = sorted(e['peak_size_rad_s'] for e in transients)
        print('  transient peak size-driven expansion: median %.2f, max %.2f rad/s' % (peaks[len(peaks)//2], peaks[-1]))
    edges = ('<%g' % DISTANCE_BINS[0],) + tuple('%g-%g' % pair for pair in zip(DISTANCE_BINS, DISTANCE_BINS[1:])) \
        + ('>=%g' % DISTANCE_BINS[-1],)
    print('  escape onset %.2f-%.2f s after the sample, among evaluated samples, by horizontal distance (units):'
          % LATENCY_S)
    print('    %-22s %s | %s' % ('group', ' | '.join('%13s' % e for e in edges), 'all'))
    pooled = {g: [[sum(r['groups'][g][b][i] for r in results) for i in (0, 1)] for b in range(len(edges))] for g in GROUPS}
    for g in GROUPS:
        cells = pooled[g]
        total = [sum(c[0] for c in cells), sum(c[1] for c in cells)]
        fmt = lambda c: '%4d/%-4d %3s' % (c[1], c[0], ('%d%%' % round(100*c[1]/c[0])) if c[0] else '-')
        print('    %-22s %s | %s' % (g, ' | '.join('%13s' % fmt(c) for c in cells), fmt(total)))
    base = pooled['baseline hover']
    for g in ('transients', 'reversal spins'):
        excess = sum(c[1] - c[0]*base[b][1]/base[b][0] for b, c in enumerate(pooled[g]) if base[b][0])
        print('  escapes added by %s over the distance-matched baseline: %.1f (%.2f/min)' % (g, excess, per_min(excess)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', type=Path, nargs='+')
    parser.add_argument('--all-modes', action='store_true', help="also count recordings whose mode is not 'play'")
    parser.add_argument('--list', action='store_true', help='print every stop-rotation transient')
    args = parser.parse_args()
    results, seen = [], {}
    for folder in sessions(args.paths):
        try:
            manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
            if manifest.get('mode') != 'play' and not args.all_modes:
                print('skipped', folder.name, '(mode %s: not human play)' % manifest.get('mode'))
                continue
            fingerprint = input_fingerprint(folder)
            if fingerprint in seen:
                print('skipped', folder.name, '(same input stream as %s)' % seen[fingerprint])
                continue
            seen[fingerprint] = folder.name
            result = audit(folder, manifest)
        except (KeyError, TypeError, FileNotFoundError) as error:
            print('skipped', folder.name, '(missing field or file: %s)' % error)
            continue
        results.append(result)
        eps = result['episodes']
        st = [e for e in eps if e['transient']]
        print('%s | config %s (%s) | hover %.1f min | axis flips %d (near %d) | size-driven episodes %d | '
              'transients %d (reversal spins %d, evaluated %d, escape %.2f-%.2f s %d) | escape onsets %d'
              % (result['session'], result['config_version'], result['runtime'], result['hover_minutes'],
                 result['axis_flips'], result['axis_flips_near'], len(eps), len(st), sum(e['reversal'] for e in st),
                 sum(e['response'] is not None for e in st), *LATENCY_S,
                 sum(e['response'] not in (None, False) for e in st), result['escape_onsets']))
        if args.list:
            for e in st:
                outcome = {None: 'not evaluated', False: '-'}.get(e['response'], None) or 'after %.2f s' % e['response']
                print('    %s: ep %d tick %d | peak %.2f rad/s | %d ticks | %.0f units | swing %.0f deg, net %.0f deg'
                      ' | escape %s' % ('reversal spin' if e['reversal'] else 'transient', e['episode'], e['tick'],
                                        e['peak_size_rad_s'], e['ticks'], e['horizontal_units'], e['swing_degrees'],
                                        e['net_axis_degrees'], outcome))
    report('ACCEPTED RUNTIME (elevation-aware tilt, N4B1C decoder)', [r for r in results if r['runtime'] == 'accepted'])
    report('EARLIER RUNTIMES', [r for r in results if r['runtime'] == 'earlier'])


if __name__ == '__main__':
    main()
