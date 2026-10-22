"""M3.2 calibration targets: peak times of the Ache et al. 2019 giant-fiber model.

Evaluates the published GF membrane-potential model (Ache et al. 2019, Curr Biol 29:1073,
doi:10.1016/j.cub.2019.01.079, STAR Methods equations 3-7) on the paper's looming stimulus: a
dark disk expanding at constant l/v from 10 to 90 degrees, then held. It prints the time of the
model's peak relative to the virtual collision (180 degrees), the M3.2 calibration target of
game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md, and the components' shares at the peak.

Pure numerics: no runtime import, no game state.

    python tools/m3_2_ache_targets.py
"""
from __future__ import annotations

import json
import math

import numpy as np

# Equation 3: LC4, a linear function of angular velocity (mV per deg/s), delay in s.
C1, DELAY_1 = 0.0002567, 0.019
# Equation 4: LPLC2, a Gaussian of log angular size (mV, deg, ln units), delay in s.
C2, C3, C4, DELAY_2 = 1.7, 42.0, 0.52, 0.019
# Equation 5: tonic inhibition, a sigmoid of angular size independent of LC4 and LPLC2.
C5, C6, C7, C8, DELAY_3 = -0.53, 0.59, 66.0, -11.0, 0.0375
# Equation 6: a small LC4-dependent inhibitory Gaussian of angular size.
C9, C10, C11, DELAY_4 = -0.52, 26.0, 7.8, 0.011
# Equation 7: weights of the four components.
W_LPLC2, W_LC4, W_I1, W_I2 = 1.45, 1.62, 2.27, 1.0
SMOOTH_S = 0.0025                     # "smoothed using a 2.5-ms time window"
STEP_S = 1e-4

CALIBRATION_LV_MS = (10, 20, 40, 80)
HELD_OUT_LV_MS = (15, 30, 60)


def stimulus(lv, start_deg=10.0, stop_deg=90.0, pre_s=0.3, hold_s=0.5):
    """Angular size in degrees on a fine grid; t = 0 when the virtual object reaches 180 deg."""
    t_start = -lv / math.tan(math.radians(start_deg / 2))
    t_stop = -lv / math.tan(math.radians(stop_deg / 2))
    t = np.arange(t_start - pre_s, t_stop + hold_s, STEP_S)
    expanding = 2.0 * np.degrees(np.arctan(lv / np.maximum(-t, 1e-12)))
    theta = np.where(t < t_start, start_deg, np.where(t < t_stop, expanding, stop_deg))
    return t, theta


def delayed(t, x, delay):
    return np.interp(t - delay, t, x, left=x[0])


def components(lv):
    """The four weighted components (mV) and their smoothed sum, on the stimulus grid."""
    t, theta = stimulus(lv)
    theta_dot = np.gradient(theta, STEP_S)
    lc4 = W_LC4 * C1 * delayed(t, theta_dot, DELAY_1)
    lplc2 = W_LPLC2 * C2 * np.exp(-(np.log(delayed(t, theta, DELAY_2)) - math.log(C3)) ** 2
                                  / (2 * C4 ** 2))
    i1 = W_I1 * (C5 + C6 / (1 + np.exp(-(delayed(t, theta, DELAY_3) - C7) / C8)))
    i2 = W_I2 * C9 * np.exp(-(delayed(t, theta, DELAY_4) - C10) ** 2 / (2 * C11 ** 2))
    n = int(round(SMOOTH_S / STEP_S))
    total = np.convolve(lplc2 + lc4 + i1 + i2, np.ones(n) / n, mode='same')
    return t, theta, total, lplc2, lc4


def targets(lvs_ms):
    rows = []
    for lv_ms in lvs_ms:
        t, theta, total, lplc2, lc4 = components(lv_ms / 1000.0)
        i = int(np.argmax(total))
        rows.append({'lv_ms': lv_ms, 'peak_time_ms': round(float(t[i]) * 1000, 1),
                     'size_at_peak_deg': round(float(theta[i]), 1),
                     'peak_mv': round(float(total[i]), 2),
                     'lplc2_share': round(float(lplc2[i] / (lplc2[i] + lc4[i])), 2)})
    return rows


def implied_threshold(rows):
    """The M3.0 E2 fit applied to the peak times: t_before = alpha * l/v + delta."""
    x = np.array([r['lv_ms'] for r in rows]) / 1000.0
    y = -np.array([r['peak_time_ms'] for r in rows]) / 1000.0
    alpha, delta = np.polyfit(x, y, 1)
    return {'alpha': round(float(alpha), 2), 'delta_ms': round(float(delta) * 1000, 1),
            'theta_threshold_deg': round(math.degrees(2 * math.atan(1 / alpha)), 1)}


def main():
    calibration, held_out = targets(CALIBRATION_LV_MS), targets(HELD_OUT_LV_MS)
    print(json.dumps({'calibration': calibration, 'held_out': held_out,
                      'implied_by_calibration_targets': implied_threshold(calibration)}, indent=1))


if __name__ == '__main__':
    main()
