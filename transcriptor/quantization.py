import math
import pretty_midi

def round_clean_duration(dur):
    """Round a power-of-2 beat duration to the nearest standard note value."""
    _CLEAN = [4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5, 0.375, 0.25, 0.1875, 0.125]
    if dur < 0.0625:
        return 0.125
    return min(_CLEAN, key=lambda x: abs(x - dur))

def apply_adaptive_quantization(pm, constant_bpm=112.0):
    """Quantise PrettyMIDI notes to 8th, 16th, or triplet-8th grid per beat.
    
    Modifies the notes of the PrettyMIDI object in-place and returns the grid classification map.
    
    Args:
        pm (pretty_midi.PrettyMIDI): PrettyMIDI object.
        constant_bpm (float): Tempo of the MIDI.
        
    Returns:
        dict: A map from beat index to grid type ('8TH', '16TH', 'TRIPLET').
    """
    print("Applying adaptive rhythm quantisation…")
    spb = 60.0 / constant_bpm

    all_notes = [n for inst in pm.instruments for n in inst.notes]
    if not all_notes:
        return {}

    # Identify unique onset times
    onsets = []
    for n in all_notes:
        sb = n.start / spb
        if not any(abs(o - sb) < 0.05 for o in onsets):
            onsets.append(sb)
    onsets = sorted(onsets)

    max_beat = int(math.ceil(max(onsets) if onsets else 0)) + 1
    beat_grids = {}
    for b in range(max_beat):
        b_onsets = [o for o in onsets if b - 0.05 <= o < b + 1.05]
        iois = [b_onsets[k] - b_onsets[k-1] for k in range(1, len(b_onsets))]
        if len(b_onsets) >= 4:
            beat_grids[b] = '16TH'
        elif len(b_onsets) == 3:
            # Check if intervals between onsets resemble triplet spacings (~0.33 beats)
            if any(0.28 <= ioi < 0.38 for ioi in iois):
                beat_grids[b] = 'TRIPLET'
            else:
                beat_grids[b] = '16TH'
        elif len(b_onsets) == 2:
            if iois[0] < 0.35:
                beat_grids[b] = '16TH'
            else:
                beat_grids[b] = '8TH'
        else:
            beat_grids[b] = '8TH'

    quantised = {}
    for o in onsets:
        b = int(math.floor(o))
        grid = beat_grids.get(b, '8TH')
        if grid == 'TRIPLET':
            q_val = b + round((o - b) * 3) / 3.0
            step = 1.0 / 3.0
        elif grid == '16TH':
            q_val = b + round((o - b) * 4) / 4.0
            step = 0.25
        else:
            q_val = b + round((o - b) * 2) / 2.0
            step = 0.5
        quantised[o] = (q_val, grid, step)

    for inst in pm.instruments:
        for n in inst.notes:
            sb = n.start / spb
            dur = (n.end - n.start) / spb
            closest = min(onsets, key=lambda x: abs(x - sb))
            q_start, grid, step = quantised[closest]

            if grid == 'TRIPLET':
                q_dur = 1.0 / 3.0
            elif grid == '8TH':
                q_dur = round_clean_duration(max(0.5, round(dur * 2) / 2.0))
            else:
                q_dur = round_clean_duration(max(0.25, round(dur * 4) / 4.0))

            n.start = q_start * spb
            n.end   = (q_start + q_dur) * spb
            if n.end <= n.start:
                n.end = n.start + step * spb

    return beat_grids
