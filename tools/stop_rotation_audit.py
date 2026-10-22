"""Read-only audit of the swatter stop-rotation transient in recorded human play.

Diagnostic only. It reads recorded ROOM sessions, writes nothing, and changes neither the frozen
M1.7.1 swatter nor any tilt geometry. It answers the open question of M1.8-N4B6
(wip/m1-4-enclosure, game/M1_8_N4B6_CONTROLLED_SLOW_APPROACH.md section 4): how often real play
produces the stop-rotation transient, in which the hovering paddle swings its axis by about 90
degrees while it corrects an overshoot and so grows in apparent size at constant range
(0.35 rad/s of size-driven expansion in the orbit control, with an escape in 17 of 48 trials).

For every recorded tick in the approach (hover) phase with a live, airborne fly it measures:

* the paddle axis rotation, modulo 180 degrees because the tilt term uses |sin(bearing - axis)|;
  an *axis flip* is a rotation of at least 60 degrees within 0.3 s;
* the image expansion the policy saw, split into range-driven and apparent-size-driven parts with
  the paddle half-size recovered from the recorded retina angle (positions are post-physics, the
  retina is projected before physics from the previous tick, as the manifest states);
* a *size-driven episode*: consecutive ticks whose size-driven expansion is at least 0.2 rad/s
  while the range-driven part stays below half of it.

It reports how many size-driven episodes coincide with an axis swing of at least 60 degrees
between 0.3 s before the episode and its end (stop-rotation transients) or not, their peak size-driven rate, the horizontal distance to the paddle, and
whether a policy escape onset follows within 0.8 s (N4B6 saw responses 0.44-0.64 s after the stop).

Recordings of the M2.4-B blind test are refused until that test is unblinded
(game/M2_4_B_REOPENING.md section 4).

    python tools/stop_rotation_audit.py SESSION_OR_SESSIONS_DIRECTORY [...]
"""
import argparse
import json
import math
from pathlib import Path

FLIP_DEGREES = 60.0
FLIP_WINDOW_S = 0.3
SIZE_RATE = 0.2           # rad/s of apparent-size expansion
RANGE_FRACTION = 0.5      # the range-driven part stays below this fraction of the size part
ESCAPE_WINDOW_S = 0.8
NEAR_UNITS = 600.0        # horizontal distance treated as near the fly


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


def audit(folder):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
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
    same = lambda i, j: 0 <= i and j < n and rows[i]['episode'] == rows[j]['episode']
    hover = lambda i: rows[i]['alive'] and rows[i]['airborne'] and rows[i]['phase'] == 'approach'
    dist = lambda i: math.sqrt((rows[i]['fx']-rows[i]['sx'])**2 + (rows[i]['fy']-rows[i]['sy'])**2 + rows[i]['h']**2)
    horiz = lambda i: math.hypot(rows[i]['fx']-rows[i]['sx'], rows[i]['fy']-rows[i]['sy'])
    flips, last_flip, hover_ticks = [], -10**9, 0
    size_rate, range_rate = [0.0]*n, [0.0]*n
    for t in range(n):
        if not hover(t):
            continue
        hover_ticks += 1
        if same(t - window, t) and all(hover(j) for j in range(t - window, t + 1)):
            turned = abs(sum(axis_delta(rows[j-1]['orientation'], rows[j]['orientation'])
                             for j in range(t - window + 1, t + 1)))
            if math.degrees(turned) >= FLIP_DEGREES and t - last_flip > window:
                flips.append(t)
                last_flip = t
        if same(t - 2, t):
            a, b = t - 2, t - 1
            ra, rb = dist(a), dist(b)
            ha, hb = ra*math.tan(rows[a+1]['theta']/2), rb*math.tan(rows[b+1]['theta']/2)
            range_rate[t] = (2*math.atan(ha/rb) - 2*math.atan(ha/ra))/dt
            size_rate[t] = (2*math.atan(hb/rb) - 2*math.atan(ha/rb))/dt
    episodes, t = [], 0
    while t < n:
        if hover(t) and size_rate[t] >= SIZE_RATE and abs(range_rate[t]) < RANGE_FRACTION*size_rate[t]:
            start = t
            while t + 1 < n and same(start, t + 1) and hover(t + 1) and size_rate[t+1] >= SIZE_RATE \
                    and abs(range_rate[t+1]) < RANGE_FRACTION*size_rate[t+1]:
                t += 1
            # The axis swing and the growth overlap: count the rotation from 0.3 s before the
            # episode to its end.
            first = max(start - window, 1)
            while not same(first - 1, start):
                first += 1
            swing = abs(sum(axis_delta(rows[j-1]['orientation'], rows[j]['orientation'])
                            for j in range(first, t + 1)))
            flip = True if math.degrees(swing) >= FLIP_DEGREES else None
            escape = next((j for j in range(start, min(n, start + int(round(ESCAPE_WINDOW_S/dt)) + 1))
                           if same(start, j) and rows[j]['escape']), None)
            episodes.append({'tick': start, 'episode': rows[start]['episode'], 'ticks': t - start + 1,
                             'peak_size_rad_s': max(size_rate[start:t+1]),
                             'horizontal_units': horiz(start), 'after_axis_flip': flip is not None,
                             'escape_within_0_8_s': escape is not None,
                             'escape_delay_s': None if escape is None else (escape - start)*dt})
        t += 1
    escapes = sum(1 for i in range(n) if rows[i]['escape'])
    return {'session': folder.name, 'config_version': manifest.get('config', {}).get('config_version'),
            'hover_minutes': hover_ticks*dt/60, 'axis_flips': len(flips),
            'axis_flips_near': sum(horiz(f) < NEAR_UNITS for f in flips), 'escape_onsets': escapes,
            'size_driven_episodes': episodes}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', type=Path, nargs='+')
    args = parser.parse_args()
    totals = {'hover_minutes': 0.0, 'axis_flips': 0, 'axis_flips_near': 0, 'escape_onsets': 0}
    transients = others = 0
    transient_escapes = other_escapes = 0
    peaks = []
    for folder in sessions(args.paths):
        try:
            result = audit(folder)
        except (KeyError, FileNotFoundError) as error:
            print('skipped', folder.name, '(missing field or file: %s)' % error)
            continue
        for key in totals:
            totals[key] += result[key]
        eps = result['size_driven_episodes']
        st = [e for e in eps if e['after_axis_flip']]
        transients += len(st); others += len(eps) - len(st)
        transient_escapes += sum(e['escape_within_0_8_s'] for e in st)
        other_escapes += sum(e['escape_within_0_8_s'] for e in eps if not e['after_axis_flip'])
        peaks += [e['peak_size_rad_s'] for e in st]
        print('%s | config %s | hover %.1f min | axis flips %d (near %d) | size-driven episodes %d '
              '(after a flip %d, escape within 0.8 s %d) | escape onsets %d'
              % (result['session'], result['config_version'], result['hover_minutes'], result['axis_flips'],
                 result['axis_flips_near'], len(eps), len(st), sum(e['escape_within_0_8_s'] for e in st),
                 result['escape_onsets']))
        for e in st:
            print('    stop-rotation transient: ep %d tick %d | peak %.2f rad/s | %d ticks | %.0f units | escape %s'
                  % (e['episode'], e['tick'], e['peak_size_rad_s'], e['ticks'], e['horizontal_units'],
                     '-' if e['escape_delay_s'] is None else 'after %.2f s' % e['escape_delay_s']))
    minutes = totals['hover_minutes']
    print('\nTOTAL hover (approach phase, fly alive and airborne) %.1f min | axis flips %d (%.2f/min), near %d'
          % (minutes, totals['axis_flips'], totals['axis_flips']/minutes if minutes else float('nan'),
             totals['axis_flips_near']))
    print('size-driven episodes after an axis flip (stop-rotation transients) %d (%.2f/min), followed by an '
          'escape within 0.8 s: %d' % (transients, transients/minutes if minutes else float('nan'), transient_escapes))
    print('size-driven episodes without a flip %d, followed by an escape: %d | all escape onsets %d'
          % (others, other_escapes, totals['escape_onsets']))
    if peaks:
        peaks.sort()
        print('transient peak size-driven expansion: median %.2f, max %.2f rad/s'
              % (peaks[len(peaks)//2], peaks[-1]))


if __name__ == '__main__':
    main()
