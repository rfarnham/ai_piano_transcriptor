import math
from collections import defaultdict

# Pitch names vocabularies
_LY_NAMES_FLAT = {
    0: 'c',   1: 'des', 2: 'd',   3: 'ees', 4: 'e',   5: 'f',
    6: 'ges', 7: 'g',   8: 'aes', 9: 'a',  10: 'bes', 11: 'b',
}

_LY_NAMES_SHARP = {
    0: 'c',   1: 'cis', 2: 'd',   3: 'dis', 4: 'e',   5: 'f',
    6: 'fis', 7: 'g',   8: 'gis', 9: 'a',  10: 'ais', 11: 'b',
}

_DUR_MAP = {
    4.0:   '1',    3.5:  '2..',  3.0:  '2.',
    2.0:   '2',    1.75: '4..', 1.5:  '4.',
    1.0:   '4',    0.875:'8..', 0.75: '8.',
    0.5:   '8',    0.375:'16.', 0.25: '16',
    0.1875:'32.',  0.125:'32',
}
_DUR_INV = {v: k for k, v in _DUR_MAP.items()}
_REST_VALS = sorted(_DUR_MAP.keys(), reverse=True)

def midi_to_ly(midi_pitch, use_sharps=False):
    """MIDI pitch → LilyPond absolute-pitch name.
    
    Note: LilyPond handles visual shifting under \ottava brackets,
    so we do not apply octave shifts here.
    """
    pc = midi_pitch % 12
    oct_n = midi_pitch // 12 - 1      # C4 (Middle C) = MIDI 60 -> oct_n = 4
    names = _LY_NAMES_SHARP if use_sharps else _LY_NAMES_FLAT
    name = names[pc]
    if oct_n >= 3:
        return name + "'" * (oct_n - 3)
    return name + "," * (3 - oct_n)

def beats_to_ly_dur(beats):
    """Largest LilyPond duration code whose beat value is <= beats."""
    beats = round(beats * 16) / 16.0
    if beats in _DUR_MAP:
        return _DUR_MAP[beats]
    candidates = [(d, s) for d, s in _DUR_MAP.items() if d <= beats + 0.001]
    return max(candidates, key=lambda x: x[0])[1] if candidates else '16'

def note_tok(pitches, ly_dur, use_sharps=False):
    """Build a LilyPond note or chord token string."""
    names = [midi_to_ly(p, use_sharps) for p in sorted(pitches)]
    if len(names) == 1:
        return f'{names[0]} {ly_dur}'
    return f'< {" ".join(names)} > {ly_dur}'

def snap(v, denom=24):
    """Snap float to a rational grid (denom=24 handles 16ths, triplets, and 32nds)."""
    return round(v * denom) / denom

def decompose_rests(gap_beats):
    """Decompose a beat gap into a list of LilyPond rest tokens."""
    tokens = []
    rem = snap(gap_beats)
    for d in _REST_VALS:
        while rem >= d - 0.001:
            tokens.append(f'r {beats_to_ly_dur(d)}')
            rem = snap(rem - d)
    return tokens

def write_measure_ly(m_events, beat_total=4.0, in_ottava=0, use_sharps=False):
    """Assemble LilyPond tokens for a single measure."""
    merged_evts = {}
    for e in m_events:
        intra = snap(e[0], 12)
        if intra not in merged_evts:
            merged_evts[intra] = [set(), 0.0, e[3], e[4]]
        merged_evts[intra][0].update(e[1])
        merged_evts[intra][1] = max(merged_evts[intra][1], e[2])
        if e[3] == 'TRIPLET':
            merged_evts[intra][2] = 'TRIPLET'
        if e[4] != 0:
            merged_evts[intra][3] = e[4]

    evts = []
    for intra in sorted(merged_evts):
        pitches, dur, grid, ott = merged_evts[intra]
        evts.append((intra, sorted(list(pitches)), dur, grid, ott))

    tokens = []
    current_beat = 0.0
    i = 0

    while i < len(evts):
        intra, pitches, duration, grid, ott = evts[i]
        
        # Gap before event
        gap = snap(intra - current_beat, 12)
        if gap > 0.01:
            if grid == 'TRIPLET':
                pass # Handled below inside triplet block
            else:
                tokens.extend(decompose_rests(gap))
                current_beat = snap(current_beat + gap, 12)

        if grid != 'TRIPLET':
            want_8va = ott
            if want_8va != in_ottava:
                tokens.append(f'\\ottava #{want_8va}')
                in_ottava = want_8va

        if grid == 'TRIPLET':
            beat_floor = math.floor(intra + 1e-6)
            beat_start = float(beat_floor)
            beat_end   = float(beat_floor + 1)
            
            pre_gap = snap(beat_start - current_beat, 12)
            if pre_gap > 0.01:
                tokens.extend(decompose_rests(pre_gap))
                current_beat = snap(current_beat + pre_gap, 12)

            # Build the tuplet content for the whole beat note-by-note
            tc     = []
            cursor = beat_start

            while (i < len(evts) and evts[i][3] == 'TRIPLET'
                   and snap(evts[i][0], 12) < beat_end - 0.01):
                t_intra = snap(evts[i][0], 12)
                t_pitch = evts[i][1]
                t_ott = evts[i][4]

                inner_th = max(0, round((t_intra - cursor) * 3))
                tc.extend(['r8'] * inner_th)
                
                # Turn ottava on/off inside tuplet
                if t_ott != in_ottava:
                    tc.append(f'\\ottava #{t_ott}')
                    in_ottava = t_ott

                tc.append(note_tok(t_pitch, '8', use_sharps=use_sharps))

                cursor = t_intra + 1.0 / 3.0
                i += 1

            # Fill remainder of beat with triplet rests
            tail_th = max(0, round((beat_end - cursor) * 3))
            tc.extend(['r8'] * tail_th)

            if tc:
                tokens.append(f'\\tuplet 3/2 {{ {" ".join(tc)} }}')
            current_beat = beat_end

        else:
            # Regular (power-of-2) note or chord
            if i + 1 < len(evts):
                next_intra = snap(evts[i+1][0], 12)
                if evts[i+1][3] == 'TRIPLET':
                    next_limit = float(math.floor(next_intra + 1e-6))
                else:
                    next_limit = next_intra
                    
                if duration > next_limit - intra:
                    duration = next_limit - intra
            
            if duration > beat_total - current_beat:
                duration = beat_total - current_beat

            ly_dur  = beats_to_ly_dur(duration)
            ly_beats = _DUR_INV[ly_dur]
            
            if pitches:
                tokens.append(note_tok(pitches, ly_dur, use_sharps=use_sharps))
            else:
                tokens.append(f'r {ly_dur}')

            # Fill remainder with rests if duration doesn't map to a single note value
            remainder = snap(duration - ly_beats)
            if remainder > 0.01:
                tokens.extend(decompose_rests(remainder))

            current_beat = snap(current_beat + duration, 12)
            i += 1

    # Fill tail of measure
    tail = snap(beat_total - current_beat, 24)
    if tail > 0.01:
        if abs(tail * 8 - round(tail * 8)) < 0.05:
            tokens.extend(decompose_rests(tail))
        else:
            thirds = round(tail * 3)
            tokens.append(f'\\tuplet 3/2 {{ {" ".join(["r8"] * thirds)} }}')

    return tokens, in_ottava

def write_voice(events, total_measures, use_ottava_flags=None, use_sharps=False):
    """Write LilyPond content lines for one staff voice."""
    meas = defaultdict(list)
    for i, (offset, pitches, duration, grid) in enumerate(events):
        m     = int(offset // 4)
        intra = snap(offset % 4.0, 12)
        flag  = use_ottava_flags[i] if use_ottava_flags else 0
        meas[m].append((intra, pitches, duration, grid, flag))

    lines     = []
    in_ottava = 0
    for m_idx in range(total_measures):
        evts = meas.get(m_idx, [])
        if not evts:
            if in_ottava != 0:
                lines.append('             \\ottava #0')
                in_ottava = 0
            lines.append('             R1')
        else:
            toks, in_ottava = write_measure_ly(evts, beat_total=4.0,
                                               in_ottava=in_ottava, use_sharps=use_sharps)
            for tok in toks:
                lines.append(f'             {tok}')
        lines.append(f'             \\bar "|"  %{{ end measure {m_idx + 1} %}}')

    if in_ottava != 0:
        lines.append('             \\ottava #0')

    return '\n'.join(lines)

def write_full_ly(treble_events, bass_events, total_measures, output_ly_path, 
                  treble_ottava_flags=None, bass_ottava_flags=None,
                  key_flats=0, key_sharps=0, title="Transcription", composer="AI", bpm=112.0):
    """Write the complete LilyPond source file."""
    use_sharps = (key_sharps > 0)
    
    treble_notes = write_voice(treble_events, total_measures, treble_ottava_flags, use_sharps=use_sharps)
    bass_notes   = write_voice(bass_events,   total_measures, bass_ottava_flags, use_sharps=use_sharps)

    # Resolve LilyPond key signature command
    if key_flats > 0:
        flat_keys = {1: 'f', 2: 'bes', 3: 'ees', 4: 'aes', 5: 'des', 6: 'ges', 7: 'ces'}
        k_sig = f"{flat_keys.get(key_flats, 'ees')} \\major"
    elif key_sharps > 0:
        sharp_keys = {1: 'g', 2: 'd', 3: 'a', 4: 'e', 5: 'b', 6: 'fis', 7: 'cis'}
        k_sig = f"{sharp_keys.get(key_sharps, 'g')} \\major"
    else:
        k_sig = "c \\major"

    lines = [
        r'\version "2.26"',
        '#(set-global-staff-size 18)',
        '',
        r'\header {',
        f'  title = "{title}"',
        f'  composer = "{composer}"',
        '  tagline = "AI Piano Transcription Pipeline"',
        '}',
        '',
        r'\paper {',
        '  #(set-paper-size "letter")',
        r'  left-margin   = 18\mm',
        r'  right-margin  = 18\mm',
        r'  top-margin    = 15\mm',
        r'  bottom-margin = 15\mm',
        r'  indent        = 15\mm',
        r'  short-indent  = 5\mm',
        '  system-system-spacing.basic-distance = #12',
        '  system-system-spacing.minimum-distance = #8',
        '  ragged-last-bottom = ##t',
        '  print-page-number  = ##t',
        '  first-page-number  = 1',
        '}',
        '',
        r'\score {',
        r'  \new PianoStaff <<',
        '    \\new Staff = "treble" {',
        '      \\clef treble',
        f'      \\key {k_sig}',
        '      \\time 4/4',
        "      \\set Timing.beamExceptions = #'()",
        '      \\set Timing.beatStructure = 1,1,1,1',
        f'      \\tempo "Medium Tempo" 4 = {int(bpm)}',
        treble_notes,
        '    }',
        '    \\new Staff = "bass" {',
        '      \\clef bass',
        f'      \\key {k_sig}',
        '      \\time 4/4',
        "      \\set Timing.beamExceptions = #'()",
        '      \\set Timing.beatStructure = 1,1,1,1',
        bass_notes,
        '    }',
        '  >>',
        r'  \layout {',
        r'    \context {',
        r'      \Score',
        '      \\override BarNumber.break-visibility = #begin-of-line-visible',
        '      skipBars = ##t',
        '    }',
        '  }',
        '  \\midi {',
        f'    \\tempo 4 = {int(bpm)}',
        '  }',
        '}',
    ]

    content = '\n'.join(lines)
    with open(output_ly_path, 'w') as f:
        f.write(content)
    print(f"Written LilyPond source: {output_ly_path}")
