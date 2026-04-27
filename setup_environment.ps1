Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Whisper German Transcription Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Step 1: Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip
Write-Host ""

Write-Host "Step 2: Installing PyTorch with CUDA support..." -ForegroundColor Yellow
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
Write-Host ""

Write-Host "Step 3: Installing Whisper and dependencies..." -ForegroundColor Yellow
pip install openai-whisper ffmpeg-python
Write-Host ""

Write-Host "Step 4: Verifying installation..." -ForegroundColor Yellow
python scripts\check_environment.py
Write-Host ""

Write-Host "============================================" -ForegroundColor Green
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green