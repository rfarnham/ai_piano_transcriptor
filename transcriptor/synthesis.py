import pretty_midi
import soundfile as sf

def synthesize_midi_to_wav(input_midi_path, output_wav_path, fs=22050):
    """Synthesize a MIDI file to a WAV audio file.
    
    Args:
        input_midi_path (str): Path to the input MIDI file.
        output_wav_path (str): Path where the synthesized WAV will be saved.
        fs (int): Sample rate of the output audio.
    """
    print(f"Loading MIDI: {input_midi_path}")
    pm = pretty_midi.PrettyMIDI(input_midi_path)
    
    print("Synthesizing audio (using pretty_midi's built-in synthesizer)...")
    audio_data = pm.synthesize(fs=fs)
    
    print(f"Saving synthesized audio to: {output_wav_path}")
    sf.write(output_wav_path, audio_data, fs)
    print("Synthesis complete.")
