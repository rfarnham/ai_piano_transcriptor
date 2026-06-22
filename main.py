#!/Users/rfarnham/.gemini/antigravity/scratch/piano_transcription/.venv/bin/python
"""Unified CLI for the AI Piano Transcription & Typesetting Pipeline."""

import argparse
import math
import os
import numpy as np
import pretty_midi

from transcriptor.inference import transcribe_audio_to_midi
from transcriptor.warping import warp_midi_to_steady_tempo
from transcriptor.quantization import apply_adaptive_quantization
from transcriptor.splitting import build_events, hand_split, merge_hands_pass
from transcriptor.ottava import label_ottava
from transcriptor.lilypond import write_full_ly
from transcriptor.synthesis import synthesize_midi_to_wav

def main():
    parser = argparse.ArgumentParser(
        description="AI Piano Transcription and Typesetting Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Input/Output paths
    parser.add_argument("--input-audio", help="Path to input audio file (.wav, .mp3, etc.)")
    parser.add_argument("--input-midi", help="Path to raw MIDI file (if starting from MIDI)")
    parser.add_argument("--output-ly", default="output.ly", help="Path where the LilyPond file will be written")
    parser.add_argument("--output-warped-midi", default="warped.mid", help="Path where the steady-tempo MIDI will be saved")
    parser.add_argument("--output-synth-wav", default="warped_synth.wav", help="Path where the synthesized audio will be saved")
    
    # Musical parameters
    parser.add_argument("--bpm", type=float, default=112.0, help="Target tempo (BPM)")
    parser.add_argument("--key-flats", type=int, default=0, help="Number of flats in the key signature (0-7)")
    parser.add_argument("--key-sharps", type=int, default=0, help="Number of sharps in the key signature (0-7)")
    parser.add_argument("--title", default="Transcription", help="Title of the piece")
    parser.add_argument("--composer", default="AI Piano Transcriptor", help="Composer name")
    
    # Custom timing / options
    parser.add_argument("--custom-beats", help="Path to text file containing custom beat times (one float per line)")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip synthesizing the warped MIDI to audio")
    parser.add_argument("--device", help="Force GPU/CPU acceleration ('mps', 'cuda', 'cpu') for transcription")
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.input_audio and not args.input_midi:
        parser.error("You must provide either --input-audio or --input-midi.")
        
    raw_midi_path = args.input_midi
    
    # Phase 1: Transcribe audio to raw MIDI if audio is provided
    if args.input_audio:
        if not raw_midi_path:
            raw_midi_path = "raw_transcribed.mid"
        transcribe_audio_to_midi(
            audio_path=args.input_audio, 
            output_midi_path=raw_midi_path,
            device=args.device
        )
        
    # Phase 2: Load raw MIDI and resolve beat times
    print(f"Loading raw MIDI: {raw_midi_path}")
    pm = pretty_midi.PrettyMIDI(raw_midi_path)
    spb = 60.0 / args.bpm
    
    if args.custom_beats:
        print(f"Loading custom beat times from: {args.custom_beats}")
        with open(args.custom_beats, "r") as f:
            beat_times = [float(line.strip()) for line in f if line.strip()]
        print(f"  Loaded {len(beat_times)} beat markers.")
    else:
        # Default to a linear/constant tempo grid based on target BPM
        total_beats = int(np.ceil(pm.get_end_time() / spb)) + 20
        beat_times = [i * spb for i in range(total_beats)]
        print(f"  Using linear beat grid with {len(beat_times)} beats.")
        
    # Phase 3: Warp MIDI to steady tempo
    print("Warping MIDI to steady tempo...")
    warped_pm = warp_midi_to_steady_tempo(
        input_mid=pm,
        output_mid=None,
        beat_times=beat_times,
        target_bpm=args.bpm
    )
    
    # Phase 4: Apply adaptive quantization (triplet/16th/8th classification)
    print("Applying adaptive quantization...")
    # This modifies warped_pm in place
    beat_grids = apply_adaptive_quantization(warped_pm, constant_bpm=args.bpm)
    print(f"Saving quantized warped MIDI to: {args.output_warped_midi}")
    warped_pm.write(args.output_warped_midi)
    
    # Phase 5: Build chord events and split into staves
    print("Building note events...")
    all_events = build_events(warped_pm, beat_grids, args.bpm)
    if not all_events:
        print("No events found in MIDI file. Exiting.")
        return
        
    max_offset = max(o for o, *_ in all_events)
    total_measures = math.ceil((max_offset + 0.1) / 4.0)
    print(f"  Found {len(all_events)} events spanning {total_measures} measures.")
    
    print("Splitting notes into treble and bass staves statefully...")
    treble_events_init, bass_events_init = hand_split(all_events)
    print("Merging staves with physical hand-span constraints...")
    treble_events, bass_events = merge_hands_pass(treble_events_init, bass_events_init)
    
    # Phase 6: Label ottava brackets (hysteresis logic)
    print("Labeling treble and bass ottava brackets...")
    treble_ottava_up = label_ottava(treble_events, '8va', 91, 75, min_duration=1.5, min_notes=3)
    treble_ottava_flags = [1 if up else 0 for up in treble_ottava_up]
    
    bass_ottava_up = label_ottava(bass_events, '8va', 67, 55, min_duration=0.0, min_notes=1)
    bass_ottava_down = label_ottava(bass_events, '8vb', 36, 48, min_duration=0.0, min_notes=1)
    
    bass_ottava_flags = []
    for up, down in zip(bass_ottava_up, bass_ottava_down):
        if up:
            bass_ottava_flags.append(1)
        elif down:
            bass_ottava_flags.append(-1)
        else:
            bass_ottava_flags.append(0)
            
    # Phase 7: Write LilyPond source score
    print(f"Writing LilyPond file to: {args.output_ly}")
    write_full_ly(
        treble_events=treble_events,
        bass_events=bass_events,
        total_measures=total_measures,
        output_ly_path=args.output_ly,
        treble_ottava_flags=treble_ottava_flags,
        bass_ottava_flags=bass_ottava_flags,
        key_flats=args.key_flats,
        key_sharps=args.key_sharps,
        title=args.title,
        composer=args.composer,
        bpm=args.bpm
    )
    
    # Phase 8: Synthesize warped MIDI (optional)
    if not args.skip_synthesis:
        print("Synthesizing steady-tempo warped MIDI...")
        synthesize_midi_to_wav(args.output_warped_midi, args.output_synth_wav)
        
    print("\nTranscription and typesetting complete!")
    print(f"Output files generated:\n - {args.output_ly}\n - {args.output_warped_midi}")
    if not args.skip_synthesis:
        print(f" - {args.output_synth_wav}")

if __name__ == "__main__":
    main()
