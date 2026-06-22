import math
from collections import defaultdict
from .quantization import round_clean_duration

# Hand-span and splitting parameters
MAX_SPAN = 16    # Max simultaneous semitone span per hand (approx. a 10th)
SPLIT_MIDI = 62  # D4 - pulls Middle C into the bass clef by default

def build_events(pm, onset_grid, bpm):
    """Build note events directly from a quantised PrettyMIDI object.
    
    Returns:
        list: A list of (beat_offset, pitches, duration_beats, grid) tuples, where:
              grid ∈ {'8TH', '16TH', 'TRIPLET'}.
    """
    spb = 60.0 / bpm
    offset_data = defaultdict(lambda: {'pitches': set(), 'dur': 0.0})

    for inst in pm.instruments:
        for n in inst.notes:
            onset = round(n.start / spb, 4)
            dur   = round((n.end - n.start) / spb, 4)
            offset_data[onset]['pitches'].add(n.pitch)
            offset_data[onset]['dur'] = max(offset_data[onset]['dur'], dur)

    events = []
    for onset in sorted(offset_data):
        d        = offset_data[onset]
        pitches  = sorted(d['pitches'])
        duration = d['dur']
        b        = int(math.floor(onset + 1e-6))
        grid     = onset_grid.get(b, '8TH')
        if grid == 'TRIPLET':
            duration = 1.0 / 3.0   # canonical; ignore any MIDI rounding
        else:
            duration = round_clean_duration(duration)
        events.append((onset, pitches, duration, grid))
    return events

def hand_split(events, max_span=MAX_SPAN, split_midi=SPLIT_MIDI):
    """Split chord events into treble and bass event lists statefully."""
    treble, bass = [], []
    lh_center = 48.0  # Default C3
    rh_center = 72.0  # Default C5

    for offset, pitches, duration, grid in events:
        uniq = sorted(list(set(pitches)))
        if not uniq:
            continue

        best_s, best_pen = 0, float('inf')
        for s in range(len(uniq) + 1):
            lh, rh = uniq[:s], uniq[s:]
            pen = 0.0

            # 1. Physical span constraints
            if len(rh) > 1:
                sp = rh[-1] - rh[0]
                if sp > max_span: 
                    pen += 1000.0 * (sp - max_span)
            if len(lh) > 1:
                sp = lh[-1] - lh[0]
                if sp > max_span: 
                    pen += 100.0 * (sp - max_span)

            # 2. Stateful voice tracking (capped to allow leaps)
            if lh:
                lh_avg = sum(lh) / len(lh)
                pen += min(abs(lh_avg - lh_center), 12.0)
            if rh:
                rh_avg = sum(rh) / len(rh)
                pen += min(abs(rh_avg - rh_center), 12.0)

            # 3. Natural gravity (mild bias pulling notes toward natural clef)
            for p in lh:
                if p >= split_midi: 
                    pen += (p - split_midi) * 0.5
            for p in rh:
                if p < split_midi: 
                    pen += (split_midi - p) * 0.5

            if pen < best_pen:
                best_pen = pen
                best_s = s

        lh = list(uniq[:best_s])
        rh = list(uniq[best_s:])

        # Hard-enforce max span by dropping inner voices if they exceed span
        if len(rh) > 1 and rh[-1] - rh[0] > max_span:
            top = rh[-1]
            rh = [p for p in rh if top - p <= max_span]
        if len(lh) > 1 and lh[-1] - lh[0] > max_span:
            bot = lh[0]
            lh = [p for p in lh if p - bot <= max_span]

        # Update voice centers
        if lh:
            lh_center = 0.5 * lh_center + 0.5 * (sum(lh) / len(lh))
        else:
            lh_center = 0.9 * lh_center + 0.1 * 48.0
            
        if rh:
            rh_center = 0.5 * rh_center + 0.5 * (sum(rh) / len(rh))
        else:
            rh_center = 0.9 * rh_center + 0.1 * 72.0

        if rh: 
            treble.append((offset, rh, duration, grid))
        if lh: 
            bass.append((offset, lh, duration, grid))

    return treble, bass

def merge_hands_pass(treble, bass, max_span=MAX_SPAN):
    """Post-processing pass to merge notes into one clef if they fit within MAX_SPAN
    and do not disrupt a continuous voice in the other hand."""
    tr_dict = {o: p for o, p, d, g in treble}
    ba_dict = {o: p for o, p, d, g in bass}
    
    meta = {}
    for o, p, d, g in treble: 
        meta[o] = (d, g)
    for o, p, d, g in bass: 
        meta[o] = (d, g)
    
    all_offsets = sorted(list(set(tr_dict.keys()) | set(ba_dict.keys())))
    
    new_tr = {}
    new_ba = {}
    
    MIN_TREBLE = 55  # G3
    MAX_BASS = 72    # C5
    WINDOW = 4.0
    GAP_THRESHOLD = 2.5
    
    def find_neighbors(t, hand_dict):
        past_t = [ot for ot in all_offsets if ot < t and ot in hand_dict and hand_dict[ot]]
        fut_t = [ot for ot in all_offsets if ot > t and ot in hand_dict and hand_dict[ot]]
        
        past_res = None
        if past_t:
            pt = past_t[-1]
            if t - pt <= WINDOW:
                past_res = (t - pt, hand_dict[pt])
                
        fut_res = None
        if fut_t:
            ft = fut_t[0]
            if ft - t <= WINDOW:
                fut_res = (ft - t, hand_dict[ft])
                
        return past_res, fut_res

    def is_mergeable_treble(pitches):
        if not pitches: 
            return False
        return (max(pitches) - min(pitches) <= max_span) and (min(pitches) >= MIN_TREBLE)

    def is_mergeable_bass(pitches):
        if not pitches: 
            return False
        return (max(pitches) - min(pitches) <= max_span) and (max(pitches) <= MAX_BASS)

    def get_hand_penalty(notes, past_res, fut_res, default_center):
        if notes:
            pen = 0.0
            if past_res:
                dt, p_notes = past_res
                p_dist = min(abs(n1 - n2) for n1 in notes for n2 in p_notes)
                pen += p_dist * math.exp(-dt)
            else:
                p_dist = abs(sum(notes)/len(notes) - default_center)
                pen += 0.1 * p_dist
            if fut_res:
                dt, f_notes = fut_res
                p_dist = min(abs(n1 - n2) for n1 in notes for n2 in f_notes)
                pen += p_dist * math.exp(-dt)
            else:
                p_dist = abs(sum(notes)/len(notes) - default_center)
                pen += 0.1 * p_dist
            return pen
        else:
            if past_res and fut_res:
                dt_p, _ = past_res
                dt_f, _ = fut_res
                gap = dt_p + dt_f
                if gap <= GAP_THRESHOLD:
                    return 10.0 * (GAP_THRESHOLD - gap)
            return 0.0

    for t in all_offsets:
        lh = ba_dict.get(t, [])
        rh = tr_dict.get(t, [])
        all_p = sorted(list(set(lh + rh)))
        
        if len(all_p) <= 1 or (max(all_p) - min(all_p) > max_span):
            new_tr[t] = rh
            new_ba[t] = lh
            continue
            
        past_lh, fut_lh = find_neighbors(t, ba_dict)
        past_rh, fut_rh = find_neighbors(t, tr_dict)
        
        score_S = (get_hand_penalty(lh, past_lh, fut_lh, 48.0) + 
                   get_hand_penalty(rh, past_rh, fut_rh, 72.0))
                   
        if is_mergeable_treble(all_p):
            score_T = (get_hand_penalty([], past_lh, fut_lh, 48.0) + 
                       get_hand_penalty(all_p, past_rh, fut_rh, 72.0))
        else:
            score_T = float('inf')
            
        if is_mergeable_bass(all_p):
            score_B = (get_hand_penalty(all_p, past_lh, fut_lh, 48.0) + 
                       get_hand_penalty([], past_rh, fut_rh, 72.0))
        else:
            score_B = float('inf')
            
        best_score = min(score_S, score_T, score_B)
        
        if best_score == score_T:
            new_tr[t] = all_p
            new_ba[t] = []
        elif best_score == score_B:
            new_tr[t] = []
            new_ba[t] = all_p
        else:
            new_tr[t] = rh
            new_ba[t] = lh
            
    new_treble = []
    new_bass = []
    for t in all_offsets:
        d, g = meta[t]
        if new_tr.get(t): 
            new_treble.append((t, new_tr[t], d, g))
        if new_ba.get(t): 
            new_bass.append((t, new_ba[t], d, g))
        
    return new_treble, new_bass
