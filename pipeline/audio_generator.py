import os
import torch
import soundfile as sf

_model = None

def get_model():
    global _model
    if _model is None:
        from omnivoice import OmniVoice
        print("[AudioGen] Loading OmniVoice model...")
        
        # Determine device
        device = "cuda:0"
        dtype = torch.float16
        if torch.cuda.is_available():
            try:
                cap = torch.cuda.get_device_capability()
                # PyTorch 2.9+ dropped support for < sm_70 in their pre-compiled wheels.
                # The GTX 1070 is sm_61.
                if cap[0] < 7:
                    print(f"[AudioGen] Warning: GPU architecture sm_{cap[0]}{cap[1]} not supported by this PyTorch build. Falling back to CPU.")
                    device = "cpu"
                    dtype = torch.float32
            except Exception:
                device = "cpu"
                dtype = torch.float32
        else:
            device = "cpu"
            dtype = torch.float32

        _model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            device_map=device,
            dtype=dtype
        )
        print(f"[AudioGen] OmniVoice loaded on {device}.")
    return _model

def generate_voiceover(script_text: str, ref_audio_path: str, ref_text: str, output_path: str, progress_callback=None):
    """
    Generates audio using OmniVoice voice cloning.
    Passes the entire script at once.
    """
    model = get_model()

    if progress_callback:
        progress_callback("Generating audio with OmniVoice...", 0.5)

    print(f"[AudioGen] Starting voice clone for: {script_text[:50]}...")
    
    # Generate the audio array
    audio = model.generate(
        text=script_text,
        ref_audio=ref_audio_path,
        ref_text=ref_text,
    )

    if progress_callback:
        progress_callback("Saving audio file...", 0.9)

    # Save to file (audio[0] is the numpy array, sample rate is 24000)
    sf.write(output_path, audio[0], 24000)
    print(f"[AudioGen] Audio saved to {output_path}")

    if progress_callback:
        progress_callback("Done", 1.0)
    
    return True
