# Deployment — Linux + Cloudflare Tunnel

End-to-end guide for deploying the Whisper web tool on a company Linux PC and exposing it
publicly to a single colleague via Cloudflare Tunnel.

The host stays on the company LAN. Cloudflared opens an outbound tunnel to Cloudflare's
edge — no inbound ports, no firewall changes, no public IP.

---

## 1. Host prerequisites

Tested on Ubuntu 22.04 / 24.04. Other distros work; adjust package commands.

```bash
# System packages
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git

# NVIDIA driver (skip if already installed)
nvidia-smi   # if this prints your GPU, skip the next line
sudo apt install -y nvidia-driver-535   # or whichever fits your card; reboot after

# Confirm CUDA visibility
nvidia-smi
```

CUDA toolkit is **not** required — PyTorch ships its own CUDA runtime via the cu121 wheels.

---

## 2. Install the app

```bash
# Pick a stable location
sudo mkdir -p /opt
sudo chown "$USER":"$USER" /opt
git clone <your-repo-url> /opt/whisper_local_deployment
cd /opt/whisper_local_deployment

# One-shot setup: venv + PyTorch (CUDA) + faster-whisper + FastAPI
./setup_linux.sh
```

The script also copies `.env.example` to `.env` if missing.

### Configure `.env`

```bash
# Generate a strong session key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Edit .env and set:
#   WHISPER_PASSWORD       — what your colleague will type into the login screen
#   WHISPER_SECRET_KEY     — the value generated above
nano /opt/whisper_local_deployment/.env
```

### Smoke test (still local)

```bash
source venv/bin/activate
set -a; . .env; set +a
uvicorn server:app --host 127.0.0.1 --port 8000
```

In another terminal on the same host:

```bash
curl http://127.0.0.1:8000/api/health
# {"ok":true,"model":"large-v3","device":"cuda",...}
```

Stop with Ctrl-C.

---

## 3. Run as a service (systemd)

Create a dedicated user (recommended):

```bash
sudo useradd -r -s /usr/sbin/nologin whisper
sudo chown -R whisper:whisper /opt/whisper_local_deployment
```

Install the unit:

```bash
sudo cp whisper-web.service /etc/systemd/system/whisper-web.service
# If your install path or user differs, edit the unit before reload:
#   User=, Group=, WorkingDirectory=, EnvironmentFile=, ExecStart=
sudo systemctl daemon-reload
sudo systemctl enable --now whisper-web
sudo systemctl status whisper-web
sudo journalctl -u whisper-web -f
```

The first start downloads the Whisper model (~3 GB for `large-v3`) into the `whisper` user's
home / cache. Watch the journal until you see `Model loaded.`

---

## 4. Cloudflare Tunnel

You need:

- A Cloudflare account
- A domain on Cloudflare (e.g. `example.com`)
- The free plan is enough for a single user.

### 4.1 Install cloudflared

```bash
# amd64 example; pick the right .deb from
# https://github.com/cloudflare/cloudflared/releases
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
cloudflared --version
```

### 4.2 Authenticate and create the tunnel

```bash
cloudflared tunnel login          # opens a browser link — pick your domain
cloudflared tunnel create whisper-web
# Note the printed tunnel UUID and credentials JSON path.
```

### 4.3 Configure ingress

```bash
sudo mkdir -p /etc/cloudflared
sudo cp cloudflared.example.yml /etc/cloudflared/config.yml
# Move (or copy) the credentials JSON next to the config:
sudo cp ~/.cloudflared/<UUID>.json /etc/cloudflared/
# Edit /etc/cloudflared/config.yml:
#   - replace REPLACE_WITH_TUNNEL_UUID
#   - replace whisper.example.com with your hostname
sudo nano /etc/cloudflared/config.yml
```

### 4.4 Route DNS

```bash
cloudflared tunnel route dns whisper-web whisper.example.com
```

This creates a CNAME `whisper.example.com → <UUID>.cfargotunnel.com` in your zone.

### 4.5 Run as a service

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -f
```

Open `https://whisper.example.com` in a browser. You should hit the sign-in screen.

---

## 5. (Recommended) Cloudflare Access — gate by email

Protect the tool with a one-time PIN to your colleague's email **on top of** the app password.
Anyone reaching the URL must pass Cloudflare's auth before the request even gets to your host.

1. Cloudflare dashboard → **Zero Trust** → **Access** → **Applications** → **Add an application** → **Self-hosted**.
2. Application domain: `whisper.example.com`.
3. Add a policy: **Action: Allow**, **Include**: Emails → your colleague's address.
4. Save. The app is now behind Cloudflare login.

Free plan covers up to 50 users.

---

## 6. File-size note (important)

Cloudflare's edge caps request bodies at **100 MB on the Free plan** (200 MB on Pro,
500 MB on Business). This limit applies to traffic going through a Tunnel.

For longer recordings:

- Pre-compress to `.m4a` / `.mp3` (often shrinks 5–10×).
- Or upgrade the Cloudflare plan.
- Or, if needed, add chunked upload — not implemented yet.

`WHISPER_MAX_UPLOAD_MB` in `.env` is the **server-side** limit; raise/lower as you wish but
remember Cloudflare's cap applies first.

---

## 7. Operations

### Update the app

```bash
cd /opt/whisper_local_deployment
sudo -u whisper git pull
sudo -u whisper venv/bin/pip install -r requirement.txt
sudo systemctl restart whisper-web
```

### Logs

```bash
sudo journalctl -u whisper-web -f       # app
sudo journalctl -u cloudflared -f       # tunnel
```

### Health checks

```bash
# From the host
curl -s http://127.0.0.1:8000/api/health
# From the public URL (will be 401 from auth-gated endpoints, but health is open)
curl -s https://whisper.example.com/api/health
```

### Rotate the password

Edit `.env`, then `sudo systemctl restart whisper-web`. Existing sessions stay valid until
their cookie expires (default 7 days) — to invalidate them now, also rotate
`WHISPER_SECRET_KEY`.

---

## 8. Security summary

- App listens only on `127.0.0.1`. There is no inbound port open on the LAN/WAN.
- Cloudflare Tunnel is the only public path. Adding **Cloudflare Access** (§5) gives you
  identity-based gating before requests even reach the host.
- App-level auth is a shared password + HMAC-signed `HttpOnly`, `Secure`, `SameSite=Lax`
  cookie.
- Uploads are written to `/tmp/whisper_web_uploads/` and deleted immediately after the
  transcription stream closes (success, error, or client disconnect).
- Transcripts are returned in-memory to the browser; the server never stores them.
