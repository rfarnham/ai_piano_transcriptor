import numpy as np
import pretty_midi

def time_to_beat(t, beat_times):
    """Interpolate physical time to beat number based on beat markers."""
    if t <= beat_times[0]:
        dt = (beat_times[1] - beat_times[0]) if len(beat_times) > 1 else 1.0
        return (t - beat_times[0]) / dt
    if t >= beat_times[-1]:
        dt = (beat_times[-1] - beat_times[-2]) if len(beat_times) > 1 else 1.0
        return len(beat_times) - 1 + (t - beat_times[-1]) / dt
    k = np.searchsorted(beat_times, t) - 1
    return k + (t - beat_times[k]) / (beat_times[k + 1] - beat_times[k])

def warp_midi_to_steady_tempo(input_mid, output_mid, beat_times, target_bpm=112.0):
    """Warp raw MIDI note timings from rubato performance time to a steady-tempo beat grid.
    
    Args:
        input_mid (str or PrettyMIDI): Path to input MIDI or loaded PrettyMIDI object.
        output_mid (str): Path where the warped MIDI will be written.
        beat_times (list of float): Physical times of beats in the performance.
        target_bpm (float): The steady target tempo.
        
    Returns:
        pretty_midi.PrettyMIDI: The warped PrettyMIDI object.
    """
    if isinstance(input_mid, str):
        print(f"Loading raw MIDI: {input_mid}")
        pm = pretty_midi.PrettyMIDI(input_mid)
    else:
        pm = input_mid
        
    spb = 60.0 / target_bpm
    out = pretty_midi.PrettyMIDI(initial_tempo=target_bpm)

    for inst in pm.instruments:
        wi = pretty_midi.Instrument(
            program=inst.program, is_drum=inst.is_drum, name=inst.name)
        print(f"  Warping {len(inst.notes)} notes…")
        for n in inst.notes:
            vs = time_to_beat(n.start, beat_times) * spb
            ve = time_to_beat(n.end,   beat_times) * spb
            vs = max(vs, 0.0)
            if ve <= vs: 
                ve = vs + 0.01
            wi.notes.append(pretty_midi.Note(
                velocity=n.velocity, pitch=n.pitch, start=vs, end=ve))
        for cc in inst.control_changes:
            vt = max(0.0, time_to_beat(cc.time, beat_times) * spb)
            wi.control_changes.append(pretty_midi.ControlChange(
                number=cc.number, value=cc.value, time=vt))
        out.instruments.append(wi)

    if output_mid:
        print(f"Saving warped MIDI: {output_mid}")
        out.write(output_mid)
    return out
