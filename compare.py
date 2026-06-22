#!/Users/rfarnham/.gemini/antigravity/scratch/piano_transcription/.venv/bin/python
"""CLI utility to compare two MIDI files for note matching verification."""

import argparse
import sys
import pretty_midi

def get_notes_from_midi(filepath, bpm=112.0):
    pm = pretty_midi.PrettyMIDI(filepath)
    spb = 60.0 / bpm
    notes = []
    for inst in pm.instruments:
        for n in inst.notes:
            # Snap to a very fine grid of 24ths of a beat to capture rational offsets
            onset_beat = round((n.start / spb) * 24) / 24.0
            notes.append((onset_beat, n.pitch))
    return sorted(notes)

def main():
    parser = argparse.ArgumentParser(description="Verify transcription by comparing output MIDI against reference MIDI.")
    parser.add_argument("--reference", required=True, help="Path to reference MIDI file (e.g. warped performance)")
    parser.add_argument("--transcribed", required=True, help="Path to transcribed/typeset MIDI file")
    parser.add_argument("--bpm", type=float, default=112.0, help="Tempo BPM of the pieces")
    args = parser.parse_args()

    print(f"Loading reference MIDI: {args.reference}")
    try:
        ref_notes = get_notes_from_midi(args.reference, args.bpm)
    except Exception as e:
        print(f"Error loading {args.reference}: {e}")
        sys.exit(1)
        
    print(f"Loading transcribed MIDI: {args.transcribed}")
    try:
        trans_notes = get_notes_from_midi(args.transcribed, args.bpm)
    except Exception as e:
        print(f"Error loading {args.transcribed}: {e}")
        sys.exit(1)
        
    print(f"Reference file has {len(ref_notes)} notes.")
    print(f"Transcribed file has {len(trans_notes)} notes.")
    
    ref_set = set(ref_notes)
    trans_set = set(trans_notes)
    
    missing_in_trans = sorted(list(ref_set - trans_set))
    extra_in_trans = sorted(list(trans_set - ref_set))
    
    # Check for near matches (timing differences within 0.1 beats)
    true_missing = []
    for beat, pitch in missing_in_trans:
        found_near = False
        for ex_beat, ex_pitch in extra_in_trans:
            if ex_pitch == pitch and abs(ex_beat - beat) <= 0.1:
                found_near = True
                break
        if not found_near:
            true_missing.append((beat, pitch))
            
    true_extra = []
    for beat, pitch in extra_in_trans:
        found_near = False
        for m_beat, m_pitch in missing_in_trans:
            if m_pitch == pitch and abs(m_beat - beat) <= 0.1:
                found_near = True
                break
        if not found_near:
            true_extra.append((beat, pitch))
            
    exact_matches = len(ref_set & trans_set)
    timing_matches = len(missing_in_trans) - len(true_missing)
    total_matched = exact_matches + timing_matches
    match_rate = (total_matched / len(ref_notes)) * 100 if ref_notes else 100.0

    print(f"\nExact matches: {exact_matches} notes.")
    print(f"Timing-shifted matches (<= 0.1 beat difference): {timing_matches} notes.")
    print(f"Overall Accuracy: {match_rate:.2f}% ({total_matched}/{len(ref_notes)} notes matched).")
    
    if not true_missing and not true_extra:
        print("\nSUCCESS: All notes match perfectly (with minor timing differences due to tuplet/measure snapping)!")
    else:
        if true_missing:
            print(f"\nWARNING: {len(true_missing)} notes in reference MIDI are missing in transcribed MIDI:")
            for beat, pitch in true_missing[:20]:
                print(f"  Beat {beat:.3f}: Pitch {pitch} ({pretty_midi.note_number_to_name(pitch)})")
            if len(true_missing) > 20:
                print("  ...")
        if true_extra:
            print(f"\nWARNING: {len(true_extra)} extra notes in transcribed MIDI that were not in reference MIDI:")
            for beat, pitch in true_extra[:20]:
                print(f"  Beat {beat:.3f}: Pitch {pitch} ({pretty_midi.note_number_to_name(pitch)})")
            if len(true_extra) > 20:
                print("  ...")

if __name__ == '__main__':
    main()
