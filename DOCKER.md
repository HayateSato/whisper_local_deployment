# Deployment — Docker (with GPU access)

The recommended way to run the Whisper web tool on a Linux PC. The image bundles
everything: PyTorch + CUDA, faster-whisper, ffmpeg, the FastAPI app, and the static
frontend. A single `docker compose up -d` brings it online.

> **Why Docker over the systemd path?** Reproducibility. You can lift the same image
> to a new machine and only need (1) NVIDIA drivers and (2) NVIDIA Container Toolkit
> on the host. No Python/CUDA wrangling. The systemd path in [DEPLOYMENT.md](DEPLOYMENT.md)
> is still supported for hosts where Docker isn't an option.

---

## 1. Host prerequisites

A clean Ubuntu 22.04 / 24.04 host with an NVIDIA GPU.

### 1.1 NVIDIA driver

```bash
nvidia-smi   # if you see your GPU + driver version, skip ahead
```

If not installed:

```bash
sudo apt update
sudo apt install -y nvidia-driver-535      # or whichever fits your card
sudo reboot
nvidia-smi
```

CUDA toolkit on the host is **not** required — the container ships its own.

### 1.2 Docker Engine

Skip if `docker --version` already prints something.

```bash
# Official Docker install (trims a bunch of distro footguns)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker          # or log out + back in
docker --version
```

### 1.3 NVIDIA Container Toolkit

This is the bridge that exposes the host GPU to containers. **Without it, the
container will start but Whisper falls back to CPU (very slow).**

```bash
# Add Cloudflare's apt repo for the toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit

# Wire it into Docker's runtime config and restart the daemon
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 1.4 Verify GPU access from inside a container

```bash
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

If you see the same `nvidia-smi` table you saw on the host, **the GPU is wired up
correctly**. If it errors with "could not select device driver" or "unknown runtime
nvidia", re-do step 1.3 carefully and `sudo systemctl restart docker`.

---

## 2. Bring up the app

```bash
git clone <your-repo-url> /opt/whisper_local_deployment
cd /opt/whisper_local_deployment

# Configuration: copy the template and edit it
cp .env.example .env
nano .env
#   - WHISPER_PASSWORD       — what your colleague types into the login screen
#   - WHISPER_SECRET_KEY     — random key:   python3 -c "import secrets;print(secrets.token_hex(32))"
#   - (leave CLOUDFLARE_TUNNEL_TOKEN empty for now)

# Build the image (~7–8 GB, takes 5–15 min the first time depending on bandwidth)
docker compose build

# Start the app
docker compose up -d

# Watch the logs while the model loads (large-v3 is ~3 GB, downloaded once)
docker compose logs -f whisper-web
# look for:  "Model loaded."
```

Health check:

```bash
curl -s http://127.0.0.1:8000/api/health
# {"ok":true,"model":"large-v3","device":"cuda",...}
```

If `device` says `cpu`: the container can't see the GPU. Re-run step 1.4 above.

Open `http://127.0.0.1:8000` in a browser to confirm the UI loads.

---

## 3. Expose publicly via Cloudflare Tunnel

This stack ships an optional `cloudflared` sidecar. The simplest auth is the
**token method** — one long string from the Cloudflare dashboard, no credential
files to mount.

### 3.1 Create the tunnel in the Cloudflare dashboard

1. **Zero Trust** dashboard → **Networks** → **Tunnels** → **Create a tunnel**.
2. Connector type: **Cloudflared**. Click **Next**.
3. Name it `whisper-web`. Click **Save tunnel**.
4. The dashboard now shows a long install command. Copy the **token** part — it's
   the very long string after `--token`.

   ```text
   sudo cloudflared service install eyJhIjoiNTM4...   ← copy this token
   ```

5. Click **Next**.
6. **Public Hostname** tab:
   - Subdomain: `whisper`
   - Domain: pick yours
   - Type: **HTTP**
   - URL: `whisper-web:8000`     ← the compose service name + port
   - Click **Save tunnel**.

### 3.2 Plug the token into compose

```bash
# Edit .env and set:
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiNTM4...        # paste the token

# Bring the sidecar online (and restart the app cleanly while we're at it)
docker compose --profile tunnel up -d

# Verify the tunnel is healthy
docker compose logs -f cloudflared
# look for:  "Registered tunnel connection ..."
```

Open `https://whisper.<your-domain>` — you should hit the app's sign-in screen.

### 3.3 Add Cloudflare Access (strongly recommended on the free plan)

See [CLOUDFLARE_FREE.md §3.1](CLOUDFLARE_FREE.md). Two minutes in the dashboard
gates the whole site behind a one-time email PIN before requests even reach
your host.

---

## 4. Day-to-day operations

```bash
# Status
docker compose ps

# Live logs (Ctrl-C exits without affecting the container)
docker compose logs -f whisper-web
docker compose logs -f cloudflared

# Restart after .env changes
docker compose up -d

# Pull repo updates and rebuild
git pull
docker compose build
docker compose up -d

# Stop everything
docker compose down

# Stop AND remove the model cache (forces re-download next time)
docker compose down -v

# Shell inside the running container (debugging)
docker compose exec whisper-web bash
```

The named volume `whisper-models` survives `docker compose down`. The model is
downloaded exactly once (~3 GB for large-v3) and reused on every restart.

### Resource usage

| Resource | Idle | Transcribing |
| --- | --- | --- |
| GPU VRAM | ~3.5 GB (large-v3 loaded) | same |
| RAM | ~2 GB | ~3 GB |
| Disk | ~8 GB image + 3 GB volume | + temp upload (deleted after) |

### Image size

The image is ~7-8 GB. Most of that is PyTorch CUDA wheels + cuDNN. Acceptable for
ML containers; not worth optimising for a single-host deployment.

---

## 5. Troubleshooting

### `device` reports `cpu` instead of `cuda`

The container can't reach the GPU. Re-run [§1.4](#14-verify-gpu-access-from-inside-a-container).
On a fresh install, the most common miss is forgetting `sudo systemctl restart
docker` after `nvidia-ctk runtime configure`.

### `could not select device driver "nvidia" with capabilities: [[gpu]]`

NVIDIA Container Toolkit isn't installed or isn't wired into Docker. Re-do
[§1.3](#13-nvidia-container-toolkit).

### First request takes a long time

First-ever start downloads the Whisper model (~3 GB for large-v3). The
healthcheck has a 120-second `start_period` to allow this. Subsequent restarts
load the cached model in ~5-10 s.

### `OOM` / GPU runs out of memory

Set a smaller model in `.env`:

```ini
WHISPER_MODEL_SIZE=medium
```

`docker compose up -d` will pick it up on next restart. The medium model is
about 1.5 GB VRAM.

### Cloudflare upload fails at ~100 MB

Free-plan body cap. Pre-compress recordings to mono AAC 64 kbps with `ffmpeg`
before uploading. See [CLOUDFLARE_FREE.md §4](CLOUDFLARE_FREE.md).

### Image rebuilds are slow

PyTorch CUDA wheels are huge. The Dockerfile installs them in a separate layer
*before* `requirement.txt`, so editing `requirement.txt` (or app code) only
rebuilds the small layers — not torch. If you change the torch line itself,
expect the long rebuild.

---

## 6. Security checklist (Docker variant)

- [x] App container binds to `127.0.0.1:8000` on the host. Not reachable from
      the LAN. Cloudflared is the only public path.
- [x] Container runs with no extra privileges (no `--privileged`, no host
      networking).
- [x] `.env` is gitignored. Permissions: `chmod 600 .env`.
- [x] `WHISPER_PASSWORD` strong + unique. `WHISPER_SECRET_KEY` random 64 hex chars.
- [x] Cloudflare Access policy on top of the app password (see
      [CLOUDFLARE_FREE.md](CLOUDFLARE_FREE.md)).
- [x] Volume `whisper-models` only contains downloaded model weights — no
      transcripts, no audio.
- [x] Uploads land in container `/tmp` (ephemeral) and are deleted at the end
      of the SSE stream.
