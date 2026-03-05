# ============================================================
# faster-whisper implementation (active)
# ============================================================
from faster_whisper import WhisperModel
import os
import torch
from pathlib import Path
from datetime import timedelta
import time

# ============================================================
# openai-whisper implementation (commented out)
# ============================================================
# import whisper
#
# def transcribe_with_timestamps(model, audio_path, interval_seconds=300):
#     """Transcribe audio with timestamp annotations (openai-whisper)"""
#     print(f"Transcribing: {audio_path}")
#     result = model.transcribe(
#         str(audio_path),
#         language="de",    # de --> Force German language
                            # if language is omitted, Whisper auto-detects the language per ~30-second chunk.
                            # Caveats to be aware of:Detection happens per chunk (~30s), not per sentence — so if someone switches language mid-chunk, accuracy may drop
#         word_timestamps=True,
#         verbose=False
#     )
#     transcription_lines = []
#     last_timestamp_mark = 0
#     for segment in result['segments']:
#         segment_start = segment['start']
#         segment_text = segment['text'].strip()
#         if segment_start >= last_timestamp_mark + interval_seconds:
#             timestamp_str = format_timestamp(segment_start)
#             transcription_lines.append(f"\n{timestamp_str}\n")
#             last_timestamp_mark = segment_start
#         transcription_lines.append(segment_text)
#     return ' '.join(transcription_lines)
#
# # Load model (openai-whisper):
# # model = whisper.load_model(model_size, device=device)
# ============================================================


def format_timestamp(seconds):
    """Convert seconds to [HH:MM:SS] format"""
    td = timedelta(seconds=int(seconds))
    return f"[{str(td)}]"


def transcribe_with_timestamps(model, audio_path, interval_seconds=300):
    """
    Transcribe audio with timestamp annotations

    Args:
        model: Loaded faster-whisper WhisperModel
        audio_path: Path to audio file
        interval_seconds: Interval for timestamp annotations (default 300 = 5 minutes)
    """
    print(f"Transcribing: {audio_path}")

    # Transcribe with word-level timestamps
    # No language specified — auto-detects per segment (handles German/English mixing)
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        beam_size=5,
    )

    print(f"    Detected language: {info.language} (probability: {info.language_probability:.2f})")

    # Build transcription with interval timestamps
    transcription_lines = []
    last_timestamp_mark = 0

    for segment in segments:
        segment_start = segment.start
        segment_text = segment.text.strip()

        # Add timestamp marker if we've crossed an interval
        if segment_start >= last_timestamp_mark + interval_seconds:
            timestamp_str = format_timestamp(segment_start)
            transcription_lines.append(f"\n{timestamp_str}\n")
            last_timestamp_mark = segment_start

        transcription_lines.append(segment_text)

    return ' '.join(transcription_lines)


def process_directory(base_path, output_base_path, model_size="large-v3", timestamp_interval=300, file_extensions=None):
    """
    Process all audio/video files in directory structure

    Args:
        base_path: Root directory containing section folders with media files
        output_base_path: Root directory for output text files (mirrors input structure)
        model_size: Whisper model size (options: tiny, base, small, medium, large, large-v2, large-v3)
        timestamp_interval: Seconds between timestamp annotations (default 300 = 5 min)
        file_extensions: List of file extensions to process (default: ['.mp3', '.mp4', '.wav', '.m4a'])
    """

    if file_extensions is None:
        file_extensions = ['.mp3', '.mp4', '.wav', '.m4a']

    # Check GPU availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"Using device: {device} | compute_type: {compute_type}")

    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"CUDA Version: {torch.version.cuda}")
        print(f"Available GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")

    # Load model
    print(f"\nLoading Whisper {model_size} model...")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    print("Model loaded successfully!\n")

    # Find all media files
    base_path = Path(base_path)
    media_files = []
    for ext in file_extensions:
        media_files.extend(base_path.rglob(f"*{ext}"))

    # Sort files for consistent processing order
    media_files.sort()

    if not media_files:
        print(f"No media files found in {base_path}")
        print(f"Looking for extensions: {', '.join(file_extensions)}")
        return

    print(f"Found {len(media_files)} media files to process")
    print(f"File types: {', '.join(file_extensions)}\n")
    print("=" * 80)

    # Process each file
    total_start_time = time.time()

    for idx, media_path in enumerate(media_files, 1):
        file_start_time = time.time()

        # Create output path mirroring input structure
        relative_path = media_path.relative_to(base_path)
        output_path = Path(output_base_path) / relative_path.with_suffix('.txt')
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Skip if already processed
        if output_path.exists():
            print(f"[{idx}/{len(media_files)}] SKIPPED (already exists): {media_path.name}")
            continue

        print(f"[{idx}/{len(media_files)}] Processing: {relative_path}")

        try:
            # Transcribe
            transcription = transcribe_with_timestamps(
                model,
                media_path,
                interval_seconds=timestamp_interval
            )

            # Save to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(transcription)

            file_duration = time.time() - file_start_time
            print(f"    Completed in {file_duration:.1f}s -> {output_path}")
            print(f"    Progress: {idx}/{len(media_files)} ({idx/len(media_files)*100:.1f}%)")

        except Exception as e:
            print(f"    ERROR: {str(e)}")
            # Log error to file
            error_log = output_path.with_suffix('.error.txt')
            with open(error_log, 'w', encoding='utf-8') as f:
                f.write(f"Error processing {media_path}:\n{str(e)}")

        print("-" * 80)

    total_duration = time.time() - total_start_time
    print(f"\n{'=' * 80}")
    print(f"COMPLETE! Total time: {total_duration/3600:.2f} hours")
    print(f"Average time per file: {total_duration/len(media_files):.1f}s")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    # Configuration
    MEDIA_BASE_PATH = r"C:\Users\hayat\Documents\Sound Recordings\tinCausa_biweekly_meeting"
    # MEDIA_BASE_PATH = r"C:\Users\hayat\Downloads\voice_record"
    OUTPUT_BASE_PATH = r"C:\Users\hayat\Documents\TinCausa_local\MeetingMinutes\meeting_transcript"
    # OUTPUT_BASE_PATH = r"C:\Users\hayat\OneDrive - MCS Data Labs GmbH\law_materials\transcript_voice_record"

    # Model selection:
    # - "large-v3": Best quality, ~4GB VRAM with float16 (RECOMMENDED)
    # - "large-v2": Slightly older, similar quality
    # - "medium": Faster, ~2GB VRAM, good quality
    # - "small": Even faster, lower quality

    MODEL_SIZE = "large-v3"

    # Timestamp interval in seconds (300 = 5 minutes)
    TIMESTAMP_INTERVAL = 300

    # File types to process
    FILE_EXTENSIONS = ['.mp4', '.mp3', '.wav', '.m4a']

    # Start processing
    process_directory(
        base_path=MEDIA_BASE_PATH,
        output_base_path=OUTPUT_BASE_PATH,
        model_size=MODEL_SIZE,
        timestamp_interval=TIMESTAMP_INTERVAL,
        file_extensions=FILE_EXTENSIONS
    )
