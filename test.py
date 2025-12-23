# test_single_file.py
import whisper
import torch

# Check GPU
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {device}")

if device == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# Load model
model = whisper.load_model("large-v3", device=device)

# Test transcribe single file
result = model.transcribe(
    r"C:\path\to\test\file.mp3",  # UPDATE THIS
    language="de",
    verbose=True
)

print("\nTranscription:")
print(result['text'])