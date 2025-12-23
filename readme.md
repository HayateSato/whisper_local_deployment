## Usage Instructions

### Update the paths in the script:

MP3_BASE_PATH: Your mp3_location folder
OUTPUT_BASE_PATH: Where you want transcriptions saved


Run the script:

```bash   
python transcribe.py
```

### Expected Performance

With your RTX 5090 and the `large-v3` model:
- **Speed**: Approximately 2-10x real-time (a 60-min file processes in 6-30 minutes)
- **Total time estimate**: 300 files × 60 min = 18,000 minutes of audio
  - Processing time: ~30-150 hours (1.3-6.3 days of continuous running)
- **Quality**: Best available for German transcription

### Model Recommendations for German

Given your dataset size (300 hours) and hardware:

**Use `large-v3`** - It's optimized for German and your RTX 5090 can handle it easily. This will give you the best accuracy, which is crucial for 300 hours of data.

### Output Format Example
```bash
[00:00:00]
Dies ist der Anfang der Aufnahme. Der Sprecher beginnt mit einer Einleitung...

[00:05:00]
Nach fünf Minuten wird das Thema vertieft. Es werden verschiedene Aspekte diskutiert...

[00:10:00]
Weitere Details werden erklärt...
Troubleshooting
GPU not detected:
bashpython -c "import torch; print(torch.cuda.is_available())"
Out of memory error:
Change model to medium:
pythonMODEL_SIZE = "medium"
Resume interrupted processing:
The script automatically skips already-transcribed files, so you can safely restart it.
```


----



### Usage Summary
**Recommended Installation Flow:**

#### 1. Install Chocolatey (if not installed):

```bash   # Run in PowerShell as Administrator
   Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```
#### 2. Install FFmpeg:
```bash
powershell   choco install ffmpeg -y
```
#### 3. Run the setup script:
```bash
bash   # If using batch file
   setup_environment.bat
   
   # Or if using PowerShell
   .\setup_environment.ps1
```
#### 4. Verify everything works:
```bash
bash   python check_environment.py
```
#### 5. Start transcribing:
```bash
bash   python transcribe.py
```