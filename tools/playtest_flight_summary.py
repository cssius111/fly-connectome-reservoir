"""Read-only flight-speed and self-approach summary of one recorded ROOM session.

Diagnostic only. It reads a session directory written by `game.app --record`, writes
nothing, and must never be used to tune toward hit rate, survival, escape rate or player
difficulty. It answers playtest questions about the M1.8-B runtime:

* how airborne time and flight speed split across the ecological states, including the
  TRANSIT bouts (count, steady speed, net displacement, straightness);
* whether the M1.8-B3a property holds in the session: no ecology ALERT entry without a
  requested or executing saccade;
* for every escape onset, whether a strike was in progress, and over the preceding 120 ms
  how much of the closing came from the fly's own motion against the paddle's, and how
  much of the image expansion came from range against apparent size (the split of the
  paired free-flight check, categories C and D; here the window ends at the positions the
  policy saw, while that check's window also includes the onset tick);
* every entry within 310 units (the N4B4 near pass) of a paddle with no strike in
  progress, and whether the fly's own motion closed most of the distance;
* the number of self-approach escapes expected from the paired free-flight check, given
  the time the paddle was parked while the fly was airborne.

Fly and paddle positions are post-physics; the retina is projected before physics from the
previous tick's positions (see the manifest's `time_alignment`), and the apparent paddle
half-size is recovered from the recorded retina angle.

    python tools/playtest_flight_summary.py results/game/sessions/SESSION_ID
"""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

NEAR_PASS_UNITS = 310.0   # N4B4: twice the paddle-plus-body collision radius
WINDOW_TICKS = 6          # 120 ms at 50 Hz, the escape classification window
LEAD_TICKS = 25           # 0.5 s of motion before a near-pass entry
PARKED_UNITS_S = 5.0      # approach-phase paddle speed below which the paddle counts as parked
STEADY_SECONDS = 1.0      # TRANSIT speed is reported after this long in a bout
# Paired free-flight check of M1.8-B3a (results/game/M1_8_B3A.md section 6): 8 category D
# escapes in 240 alive minutes under config_version 19, the pointer parked.
FREE_FLIGHT_SELF_APPROACH_PER_MIN = 8 / 240.0


def load(folder):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    rows = []
    with (folder / 'ticks.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            r = json.loads(line)
            fly, sw, eco = r['fly'], r['swatter'], r['ecology']
            rows.append({'episode': r['episode'], 'tick': r['tick'], 'alive': fly['alive'],
                         'airborne': r['lifecycle']['airborne'], 'lifecycle': r['lifecycle']['mode'],
                         'ecology': eco['state'], 'speed': fly['speed_bl_s'],
                         'requested': eco['requested_speed_bl_s'], 'fx': fly['x'], 'fy': fly['y'],
                         'sx': sw['x'], 'sy': sw['y'], 'height': sw['height'], 'paddle_speed': sw['speed'],
                         'phase': sw['phase'], 'theta': r['retina']['theta'],
                         'saccade_requested': r['action']['saccade'] != 0, 'saccade': r['saccade']['type'],
                         'escape_onset': r['event_flags']['escape_onset'],
                         'alert_onset': r['event_flags']['alert_onset'], 'paused': r['paused']})
    episodes = [json.loads(line) for line in
                (folder / 'episodes.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    return manifest, rows, episodes


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q / 100 * (len(values) - 1))))] if values else float('nan')


class Geometry:
    def __init__(self, rows):
        self.rows = rows

    def same_episode(self, i, j):
        return 0 <= i and j < len(self.rows) and self.rows[i]['episode'] == self.rows[j]['episode']

    def distance(self, fly_row, paddle_row):
        a, b = self.rows[fly_row], self.rows[paddle_row]
        return math.sqrt((a['fx'] - b['sx'])**2 + (a['fy'] - b['sy'])**2 + b['height']**2)

    def horizontal(self, i):
        r = self.rows[i]
        return math.hypot(r['fx'] - r['sx'], r['fy'] - r['sy'])

    def closing(self, first, last):
        """3D distance closed by the fly's own motion and by the paddle's, rows first -> last."""
        by_fly = by_paddle = 0.0
        for j in range(first + 1, last + 1):
            fly_moved = self.distance(j, j - 1)
            by_fly += self.distance(j - 1, j - 1) - fly_moved
            by_paddle += fly_moved - self.distance(j, j)
        return by_fly, by_paddle

    def expansion(self, onset):
        """Range and apparent-size expansion (rad) of the image the policy saw up to `onset`."""
        rng = size = 0.0
        for b in range(onset - WINDOW_TICKS, onset):
            a = b - 1
            ra, rb = self.distance(a, a), self.distance(b, b)
            ha = ra * math.tan(self.rows[a + 1]['theta'] / 2)
            hb = rb * math.tan(self.rows[b + 1]['theta'] / 2)
            rng += 2*math.atan(ha / rb) - 2*math.atan(ha / ra)
            size += 2*math.atan(hb / rb) - 2*math.atan(ha / rb)
        return rng, size


def bouts_of(rows, airborne):
    """Contiguous airborne runs of one ecological state within one episode."""
    bouts, start, previous = defaultdict(list), None, None
    for i in airborne:
        if (previous is None or i != previous + 1 or rows[i]['ecology'] != rows[previous]['ecology']
                or rows[i]['episode'] != rows[previous]['episode']):
            if start is not None:
                bouts[rows[start]['ecology']].append((start, previous))
            start = i
        previous = i
    if start is not None:
        bouts[rows[start]['ecology']].append((start, previous))
    return bouts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('session', type=Path)
    args = parser.parse_args()
    manifest, rows, episodes = load(args.session.resolve())
    dt, body = manifest['tick_seconds'], manifest['body_length']
    geo = Geometry(rows)
    n = len(rows)
    mode = (manifest['config'].get('ecology_threat_input') or {}).get('mode', 'policy_state_v0 (block absent)')
    print('session', manifest['session_id'], '| commit', manifest['git_commit'][:7], manifest['git_branch'],
          '| dirty', manifest['git_dirty'])
    print('config_version', manifest['config_version'], '| ecology_threat_input', mode,
          '| numba_threads', manifest['runtime']['numba_threads'], '| ticks', manifest['tick_count'])

    alive = [i for i in range(n) if rows[i]['alive'] and not rows[i]['paused']]
    airborne = [i for i in alive if rows[i]['airborne']]
    parked = [i for i in airborne if rows[i]['phase'] == 'approach' and rows[i]['paddle_speed'] < PARKED_UNITS_S]
    totals = Counter()
    for episode in episodes:
        totals.update(episode['stats'])
    print('\nTIME   total %.1f s | alive %.1f s | airborne %.1f s | paddle parked while airborne %.1f s'
          ' | paused ticks %d | episodes %d (deaths %d)'
          % (n*dt, len(alive)*dt, len(airborne)*dt, len(parked)*dt, sum(r['paused'] for r in rows),
             len(episodes), sum(not e['alive'] for e in episodes)))
    print('STATS  strikes %d | hits %d | misses %d | escapes %d'
          % (totals['strikes'], totals['hits'], totals['misses'], totals['escapes']))
    print('LIFECYCLE share of alive time:',
          {k: round(v / len(alive), 3) for k, v in Counter(rows[i]['lifecycle'] for i in alive).most_common()})
    if not airborne:
        return

    bouts = bouts_of(rows, airborne)
    speeds, requested = defaultdict(list), defaultdict(list)
    for i in airborne:
        speeds[rows[i]['ecology']].append(rows[i]['speed'])
        requested[rows[i]['ecology']].append(rows[i]['requested'])
    print('\nECOLOGY (airborne)  share | bouts | mean bout s | speed BL/s mean p50 p90 max | requested mean')
    for state in sorted(speeds, key=lambda s: -len(speeds[s])):
        values, runs = speeds[state], bouts[state]
        print('  %-13s %5.1f%% | %4d | %5.2f | %5.1f %5.1f %5.1f %5.1f | %5.1f'
              % (state, 100*len(values)/len(airborne), len(runs),
                 sum(e - s + 1 for s, e in runs)*dt/max(1, len(runs)), sum(values)/len(values),
                 percentile(values, 50), percentile(values, 90), max(values),
                 sum(requested[state])/len(values)))
    every = [rows[i]['speed'] for i in airborne]
    print('ALL airborne speed BL/s: mean %.1f p50 %.1f p90 %.1f p99 %.1f max %.1f'
          ' | time above 13 BL/s %.1f%%, above 20 BL/s %.1f%%'
          % (sum(every)/len(every), percentile(every, 50), percentile(every, 90), percentile(every, 99),
             max(every), 100*sum(v > 13 for v in every)/len(every), 100*sum(v > 20 for v in every)/len(every)))
    transit = bouts.get('TRANSIT', [])
    if transit:
        skip = int(round(STEADY_SECONDS / dt))
        steady = [rows[j]['speed'] for s, e in transit for j in range(s + skip, e + 1)]
        net = [math.hypot(rows[e]['fx'] - rows[s]['fx'], rows[e]['fy'] - rows[s]['fy'])/body for s, e in transit]
        path = [sum(rows[j]['speed']*dt for j in range(s, e + 1)) for s, e in transit]
        print('TRANSIT %d bouts | speed after %.0f s in the bout: mean %.1f p90 %.1f BL/s'
              ' | net displacement mean %.1f max %.1f BL | straightness %.2f | arena width %.0f BL'
              % (len(transit), STEADY_SECONDS, sum(steady)/len(steady) if steady else float('nan'),
                 percentile(steady, 90), sum(net)/len(net), max(net),
                 sum(a/b for a, b in zip(net, path) if b > 0)/len(net), manifest['logical_arena'][0]/body))

    entries = [i for i in range(1, n) if geo.same_episode(i - 1, i)
               and rows[i]['ecology'] == 'ALERT' and rows[i - 1]['ecology'] != 'ALERT']
    unexplained = [i for i in entries if not rows[i]['saccade_requested'] and rows[i - 1]['saccade'] != 'ALERT']
    print('\nALERT  policy alert onsets %d | ecology ALERT entries %d'
          ' | entries without a requested or executing saccade %d'
          % (sum(r['alert_onset'] for r in rows), len(entries), len(unexplained)))

    print('\nESCAPES  ep tick | ecology before | paddle phase | horizontal units'
          ' | 120 ms closed by fly / paddle | range / size expansion rad | label')
    labels = Counter()
    for i in (i for i in range(n) if rows[i]['escape_onset']):
        complete = geo.same_episode(i - WINDOW_TICKS - 1, i)
        strike = any(rows[j]['phase'] != 'approach'
                     for j in range(max(0, i - WINDOW_TICKS), i + 1) if geo.same_episode(j, i))
        by_fly, by_paddle = geo.closing(i - WINDOW_TICKS - 1, i - 1) if complete else (math.nan, math.nan)
        rng, size = geo.expansion(i) if complete else (math.nan, math.nan)
        if strike:
            label = 'strike in progress'
        elif not complete:
            label = 'episode start'
        elif rng <= size:
            label = 'size-dominated'
        elif by_fly > by_paddle:
            label = 'SELF-APPROACH (fly-driven, range-dominated)'
        else:
            label = 'paddle moved toward the fly'
        labels[label] += 1
        print('  %d %5d | %-11s | %-14s | %6.0f | %6.1f / %6.1f | %.4f / %.4f | %s'
              % (rows[i]['episode'], rows[i]['tick'], rows[i - 1]['ecology'], rows[i]['phase'],
                 geo.horizontal(i - 1), by_fly, by_paddle, rng, size, label))
    print('ESCAPE labels:', dict(labels))

    passes = []
    for k, i in enumerate(airborne):
        if k == 0 or airborne[k - 1] != i - 1 or not geo.same_episode(i - LEAD_TICKS, i):
            continue
        if (geo.horizontal(i) < NEAR_PASS_UNITS <= geo.horizontal(i - 1)
                and all(rows[j]['phase'] == 'approach' for j in range(i - LEAD_TICKS, i + 1))):
            by_fly, by_paddle = geo.closing(i - LEAD_TICKS, i)
            escape = next((j for j in range(i, min(n, i + LEAD_TICKS + 1))
                           if geo.same_episode(i, j) and rows[j]['escape_onset']), None)
            passes.append((i, by_fly, by_paddle, escape))
    fly_driven = [p for p in passes if p[1] > p[2]]
    print('\nNEAR PASSES (entering %.0f units, no strike) %d | fly-driven %d'
          ' | fly-driven and followed by an escape within 0.5 s %d'
          % (NEAR_PASS_UNITS, len(passes), len(fly_driven), sum(p[3] is not None for p in fly_driven)))
    for i, by_fly, by_paddle, escape in fly_driven[:20]:
        print('  ep %d tick %5d | ecology %-11s | fly %4.1f BL/s | 0.5 s closed by fly %5.0f / paddle %5.0f | escape %s'
              % (rows[i]['episode'], rows[i]['tick'], rows[i]['ecology'], rows[i]['speed'], by_fly, by_paddle,
                 '-' if escape is None else 'tick %d' % rows[escape]['tick']))
    minutes = len(parked)*dt/60
    expected = FREE_FLIGHT_SELF_APPROACH_PER_MIN*minutes
    print('EXPECTED self-approach escapes from the paired free-flight check (%.3f/min):'
          ' %.2f in %.1f parked airborne minutes, P(none) = %.2f'
          % (FREE_FLIGHT_SELF_APPROACH_PER_MIN, expected, minutes, math.exp(-expected)))


if __name__ == '__main__':
    main()
