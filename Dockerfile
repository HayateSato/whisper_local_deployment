# syntax=docker/dockerfile:1.6
#
# Whisper Web — GPU-enabled container.
# Build:  docker build -t whisper-web .
# Run:    see docker-compose.yml (recommended) or DOCKER.md.
#
# Base: NVIDIA CUDA 12.1 + cuDNN 8 runtime on Ubuntu 22.04.
# This matches the cu121 PyTorch wheels we install below.

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # faster-whisper / HF Hub model cache lives here. Mount a volume to persist.
    HF_HOME=/cache/huggingface \
    XDG_CACHE_HOME=/cache

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ffmpeg \
        ca-certificates \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyTorch CUDA wheels — biggest layer, kept separate so requirement.txt
# changes don't invalidate it.
RUN pip install --index-url https://download.pytorch.org/whl/cu121 \
        torch torchvision torchaudio

# Application Python deps. Note: torch lines in requirement.txt are
# already satisfied by the layer above and will be skipped.
COPY requirement.txt ./
RUN pip install -r requirement.txt

# Application code (deps cached above)
COPY server.py ./
COPY static/ ./static/

# Pre-create the cache dir so the volume mount inherits permissions cleanly.
RUN mkdir -p /cache/huggingface

EXPOSE 8000

# Single worker — Whisper holds GPU state per process; multiple workers would
# duplicate the model in VRAM with no parallel speedup.
CMD ["uvicorn", "server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--timeout-keep-alive", "75"]
