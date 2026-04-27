#!/usr/bin/env bash
# One-shot setup for the Whisper web tool on a Linux host.
#   - Creates a Python venv
#   - Installs PyTorch with CUDA support (cu121 wheels)
#   - Installs the rest of requirement.txt (faster-whisper + FastAPI stack)
#   - Verifies CUDA visibility
#
# Run from the repo root:
#   chmod +x setup_linux.sh
#   ./setup_linux.sh
#
# Prereqs (install separately, see DEPLOYMENT.md):
#   - NVIDIA driver + nvidia-smi working
#   - ffmpeg     (apt install ffmpeg)
#   - python3.10+ with venv (apt install python3-venv)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${REPO_DIR}/venv"

echo "==> Repo: ${REPO_DIR}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.10+." >&2
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "WARNING: ffmpeg not found on PATH. Install it: sudo apt install ffmpeg"
fi

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "==> Creating venv at ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

echo "==> Upgrading pip"
pip install --upgrade pip

echo "==> Installing PyTorch (CUDA 12.1 wheels)"
pip install --index-url https://download.pytorch.org/whl/cu121 \
    torch torchvision torchaudio

echo "==> Installing remaining requirements"
pip install -r "${REPO_DIR}/requirement.txt"

echo "==> CUDA check"
python - <<'PY'
import torch
print(f"  torch.__version__   = {torch.__version__}")
print(f"  cuda available      = {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  cuda version        = {torch.version.cuda}")
    print(f"  device              = {torch.cuda.get_device_name(0)}")
PY

if [[ ! -f "${REPO_DIR}/.env" ]]; then
    echo "==> Creating .env from .env.example (EDIT IT before starting the server)"
    cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
fi

echo
echo "Done."
echo "Next steps:"
echo "  1. Edit ${REPO_DIR}/.env (set WHISPER_PASSWORD and WHISPER_SECRET_KEY)."
echo "  2. Smoke test:  source venv/bin/activate && set -a && . .env && set +a && \\"
echo "                  uvicorn server:app --host 127.0.0.1 --port 8000"
echo "  3. Install as a service: see DEPLOYMENT.md."
