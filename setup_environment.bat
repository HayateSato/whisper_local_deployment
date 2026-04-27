@echo off
echo ============================================
echo Whisper German Transcription Setup
echo ============================================
echo.

echo Step 1: Upgrading pip...
python -m pip install --upgrade pip
echo.

echo Step 2: Installing PyTorch with CUDA support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
echo.

echo Step 3: Installing Whisper and dependencies...
pip install openai-whisper ffmpeg-python
echo.

echo Step 4: Verifying installation...
python scripts\check_environment.py
echo.

echo ============================================
echo Setup complete!
echo ============================================
pause