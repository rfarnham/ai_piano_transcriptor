import torch
import librosa
from piano_transcription_inference import PianoTranscription, sample_rate

def detect_device():
    """Detect available hardware acceleration device (MPS, CUDA, or CPU fallback)."""
    if torch.backends.mps.is_available():
        return 'mps'
    elif torch.cuda.is_available():
        return 'cuda'
    return 'cpu'

def transcribe_audio_to_midi(audio_path, output_midi_path, device=None):
    """Transcribe a piano solo audio file into a raw MIDI file.
    
    Args:
        audio_path (str): Path to input audio (.wav, .mp3, etc.).
        output_midi_path (str): Path where the transcribed raw MIDI will be saved.
        device (str, optional): Target device ('mps', 'cuda', 'cpu'). Auto-detected if None.
    """
    if device is None:
        device = detect_device()
    print(f"Loading audio file: {audio_path}")
    audio, _ = librosa.load(path=audio_path, sr=sample_rate, mono=True)
    
    print(f"Initializing Piano Transcription model on device: {device}...")
    # This automatically downloads the Zenodo checkpoint if not present
    transcriptor = PianoTranscription(device=device, checkpoint_path=None)
    
    print("Transcribing audio (this may take a couple of minutes)...")
    transcribed_dict = transcriptor.transcribe(audio, output_midi_path)
    
    print(f"Successfully transcribed piano to: {output_midi_path}")
    return transcribed_dict
