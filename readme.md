# Whisper Local Transcription

Local-first audio transcription powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
Two ways to use it:

| Mode | Entry point | Use when |
| --- | --- | --- |
| **Web tool** | `server.py` (FastAPI + static frontend) | A colleague needs to upload one file at a time through the browser. Designed to be hosted on a Linux PC and exposed via Cloudflare Tunnel — no public IP, no port forwarding. |
| **CLI batch** | `transcribe.py` | Bulk-transcribing a whole directory tree on your own machine. Resumable: skips files that already have a `.txt` next to them. |

Both share the same model (default `large-v3`) and accept `.mp3`, `.mp4`, `.wav`, `.m4a`.

---

## Web tool

A drag-and-drop UI with live progress, detected language, and a one-click `.txt` download.

![flow](https://img.shields.io/badge/upload-stream-progress-download-4f8cff)

### Features

- **Drag-and-drop** or click-to-browse upload, with friendly errors for the wrong file type or oversized files.
- **Live progress bar** driven by Server-Sent Events — shows `current / total` audio time as the model works.
- **Detected language** + confidence shown as soon as faster-whisper returns it.
- **Cookie-based auth** with a single shared password (`WHISPER_PASSWORD`); HMAC-signed, `HttpOnly`, `Secure`, 7-day TTL.
- **Cancel** button that aborts both the request and the in-flight transcription.
- **Download `.txt`** or **Copy** the transcript to clipboard.
- Heartbeat keepalives so SSE streams survive Cloudflare's idle timeouts.

### Local smoke test

```bash
pip install -r requirement.txt

# Linux / macOS
export WHISPER_PASSWORD=Transcribe123
export WHISPER_SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
export WHISPER_COOKIE_SECURE=false   # only for plain-HTTP local testing
uvicorn server:app --host 127.0.0.1 --port 8000
```

```powershell
# Windows (PowerShell)
$env:WHISPER_PASSWORD = "Transcribe123"
$env:WHISPER_SECRET_KEY = (python -c "import secrets;print(secrets.token_hex(32))")
$env:WHISPER_COOKIE_SECURE = "false"
uvicorn server:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>, sign in with `Transcribe123`, drop a file.

### Production deployment (Linux + Cloudflare Tunnel)

The full walk-through — host prereqs, systemd, cloudflared, DNS, Cloudflare Access (recommended for email-gated colleague access), and the Cloudflare 100 MB body cap — lives in **[DEPLOYMENT.md](DEPLOYMENT.md)**.

**Don't have a paid Cloudflare account?** See **[CLOUDFLARE_FREE.md](CLOUDFLARE_FREE.md)** — it covers the secure free-plan setup (Tunnel + Access + WAF rules) with no security trade-offs except the 100 MB upload cap, plus pre-compression workarounds.

Short version:

```bash
./setup_linux.sh                                # venv + PyTorch CUDA + deps
nano .env                                       # set WHISPER_PASSWORD + WHISPER_SECRET_KEY
sudo cp whisper-web.service /etc/systemd/system/
sudo systemctl enable --now whisper-web         # app on 127.0.0.1:8000

cloudflared tunnel login
cloudflared tunnel create whisper-web
sudo cp cloudflared.example.yml /etc/cloudflared/config.yml   # edit UUID + hostname
cloudflared tunnel route dns whisper-web whisper.example.com
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

### Configuration

All settings come from environment variables (or a `.env` file loaded by the systemd unit). See **[.env.example](.env.example)** for the full list.

| Variable | Default | Notes |
| --- | --- | --- |
| `WHISPER_PASSWORD` | *(required)* | Sign-in password. |
| `WHISPER_SECRET_KEY` | *(required)* | Cookie signing key — `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `WHISPER_MODEL_SIZE` | `large-v3` | `tiny` / `base` / `small` / `medium` / `large-v2` / `large-v3`. |
| `WHISPER_TIMESTAMP_INTERVAL` | `300` | Seconds between `[hh:mm:ss]` markers. `0` disables. |
| `WHISPER_BEAM_SIZE` | `5` | faster-whisper beam size. |
| `WHISPER_MAX_UPLOAD_MB` | `1024` | Server-side cap. Cloudflare's edge cap (100 MB free / 200 MB Pro) applies first. |
| `WHISPER_COOKIE_SECURE` | `true` | Set to `false` only for plain-HTTP local testing. |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |

### API surface

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/login` | Form field `password`. Sets session cookie. |
| `POST` | `/api/logout` | Clears session cookie. |
| `GET`  | `/api/me` | `{"authenticated": bool}`. |
| `GET`  | `/api/health` | Model name, device, compute type, load state. |
| `POST` | `/api/transcribe` | Multipart `file` upload. Returns `text/event-stream` with `status` / `language` / `progress` / `complete` / `error` events. |

---

## CLI batch script

For local bulk processing on your own machine.

### Windows setup

```powershell
# 1. FFmpeg (one-time)
Set-ExecutionPolicy Bypass -Scope Process -Force
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
choco install ffmpeg -y

# 2. Python deps
.\setup_environment.ps1     # or setup_environment.bat

# 3. Sanity check
python scripts\check_environment.py
```

### Linux setup

```bash
sudo apt install -y ffmpeg python3-venv
./setup_linux.sh
```

### Run

Edit the paths at the bottom of [transcribe.py](transcribe.py):

```python
MEDIA_BASE_PATH  = r"<input directory>"   # contains .mp3/.mp4/.wav/.m4a
OUTPUT_BASE_PATH = r"<output directory>"  # mirrors input tree, .txt files
MODEL_SIZE = "large-v3"
TIMESTAMP_INTERVAL = 300                  # 5 minutes
```

Then:

```bash
python transcribe.py
```

The script auto-skips files that already have a `.txt` next to them, so you can safely Ctrl-C and resume.

---

## Model recommendation

`large-v3` is the default. On an RTX 4090 it runs at roughly 2–10× real-time — a 60-minute file completes in 6–30 minutes. It's tuned for high-accuracy multilingual transcription (handles German/English mixing well thanks to per-segment language detection).

If you're VRAM-constrained, fall back to `medium` or `small`:

```bash
# .env (web tool)
WHISPER_MODEL_SIZE=medium
```

```python
# transcribe.py (CLI)
MODEL_SIZE = "medium"
```

### Output format example

```text
[0:00:00]
Dies ist der Anfang der Aufnahme. Der Sprecher beginnt mit einer Einleitung...

[0:05:00]
Nach fünf Minuten wird das Thema vertieft...

[0:10:00]
Weitere Details werden erklärt...
```

---

## Troubleshooting

**GPU not detected**
```bash
python -c "import torch; print(torch.cuda.is_available())"
```
If `False`: reinstall PyTorch with the CUDA wheel index — `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121`.

**Out-of-memory on `large-v3`** — drop to `medium` (see above).

**SSE stream stalls behind a proxy** — the server sends `: keepalive` heartbeats every 15 s. If your reverse proxy buffers responses, disable buffering for `/api/transcribe` (Cloudflare Tunnel doesn't need this; nginx does — `proxy_buffering off`).

**Upload rejected at 100 MB** — Cloudflare Free plan body cap. Pre-compress to `.m4a` or upgrade plan. See [DEPLOYMENT.md §6](DEPLOYMENT.md).

---

## Repo layout

```
.
├── server.py                  # FastAPI app (web tool)
├── static/                    # frontend (HTML + CSS + JS, no framework)
│   ├── index.html
│   ├── app.js
│   └── style.css
├── transcribe.py              # CLI batch script
├── scripts/                   # diagnostic / dev scripts
│   ├── check_environment.py   # GPU/CUDA/ffmpeg/PyTorch sanity report
│   └── check_cuda.py          # one-liner CUDA visibility check
├── requirement.txt            # Python deps (faster-whisper, FastAPI, ...)
├── setup_environment.ps1      # Windows venv setup
├── setup_environment.bat      # Windows venv setup (cmd)
├── setup_linux.sh             # Linux venv setup
├── whisper-web.service        # systemd unit for the web tool
├── cloudflared.example.yml    # Cloudflare Tunnel ingress template
├── .env.example               # web-tool config template
├── DEPLOYMENT.md              # full Linux + Cloudflare deployment guide
└── CLOUDFLARE_FREE.md         # secure free-plan Cloudflare setup
```
