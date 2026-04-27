"""
Whisper Web — FastAPI backend.

Single-user web tool for audio transcription on a local Linux host,
exposed publicly via Cloudflare Tunnel.

Pipeline:
    upload (multipart) -> validate -> transcribe (faster-whisper)
    -> stream progress via Server-Sent Events -> client downloads .txt

Run (dev):
    uvicorn server:app --host 0.0.0.0 --port 8000

Run (prod, behind Cloudflare Tunnel):
    uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1
"""

from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import logging
import os
import secrets
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LOG = logging.getLogger("whisper_web")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a"}
MAX_UPLOAD_BYTES = int(os.environ.get("WHISPER_MAX_UPLOAD_MB", "1024")) * 1024 * 1024
MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "large-v3")
TIMESTAMP_INTERVAL = int(os.environ.get("WHISPER_TIMESTAMP_INTERVAL", "300"))
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE", "5"))

WHISPER_PASSWORD = os.environ.get("WHISPER_PASSWORD")
if not WHISPER_PASSWORD:
    raise RuntimeError(
        "WHISPER_PASSWORD is not set. "
        "Set it in the environment (or .env file loaded by systemd) before starting."
    )

# Cookie signing key. Persist across restarts so a colleague stays logged in.
SECRET_KEY = os.environ.get("WHISPER_SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    LOG.warning(
        "WHISPER_SECRET_KEY not set — generated an ephemeral one. "
        "Sessions will be invalidated on every restart."
    )

SESSION_COOKIE = "whisper_session"
SESSION_TTL_SECONDS = 7 * 24 * 3600

STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Auth (HMAC-signed cookie, single shared password)
# ---------------------------------------------------------------------------


def _sign(payload: str) -> str:
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify(token: str) -> bool:
    try:
        payload, sig = token.rsplit(".", 1)
    except ValueError:
        return False
    expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        issued_at = int(payload.split(":", 1)[1])
    except (IndexError, ValueError):
        return False
    return (time.time() - issued_at) <= SESSION_TTL_SECONDS


def _make_session_token() -> str:
    return _sign(f"v1:{int(time.time())}")


def require_auth(request: Request) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token or not _verify(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")


# ---------------------------------------------------------------------------
# Model lifecycle
# ---------------------------------------------------------------------------


class TranscriptionService:
    """Holds the loaded faster-whisper model. Loaded once at startup."""

    def __init__(self) -> None:
        self.model = None
        self.device = "cpu"
        self.compute_type = "int8"

    def load(self) -> None:
        # Imported lazily so `--help` and tests don't pay the import cost.
        from faster_whisper import WhisperModel
        try:
            import torch
            cuda = torch.cuda.is_available()
        except Exception:
            cuda = False

        self.device = "cuda" if cuda else "cpu"
        self.compute_type = "float16" if cuda else "int8"
        LOG.info("Loading Whisper %s on %s (%s)", MODEL_SIZE, self.device, self.compute_type)
        self.model = WhisperModel(MODEL_SIZE, device=self.device, compute_type=self.compute_type)
        LOG.info("Model loaded.")


service = TranscriptionService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    service.load()
    yield


app = FastAPI(title="Whisper Web", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Routes — auth
# ---------------------------------------------------------------------------


@app.post("/api/login")
async def login(password: str = Form(...)) -> Response:
    if not hmac.compare_digest(password, WHISPER_PASSWORD):
        # Constant-ish delay to slow brute force from a single attacker.
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=401, detail="invalid password")
    token = _make_session_token()
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("WHISPER_COOKIE_SECURE", "true").lower() == "true",
    )
    return resp


@app.post("/api/logout")
async def logout() -> Response:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/api/me")
async def me(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    return {"authenticated": bool(token and _verify(token))}


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "model": MODEL_SIZE,
        "device": service.device,
        "compute_type": service.compute_type,
        "model_loaded": service.model is not None,
    }


# ---------------------------------------------------------------------------
# Routes — transcription (SSE)
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _format_timestamp(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"[{h:01d}:{m:02d}:{s:02d}]"


async def _save_upload(upload: UploadFile, dest: Path) -> int:
    """Stream the upload to disk, enforcing MAX_UPLOAD_BYTES."""
    written = 0
    chunk = 1024 * 1024
    with dest.open("wb") as f:
        while True:
            buf = await upload.read(chunk)
            if not buf:
                break
            written += len(buf)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"file too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
                )
            f.write(buf)
    return written


def _validate_filename(filename: Optional[str]) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="missing filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unsupported file type '{suffix or '(none)'}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )
    return suffix


@app.post("/api/transcribe", dependencies=[Depends(require_auth)])
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    timestamp_interval: int = Form(default=TIMESTAMP_INTERVAL),
) -> StreamingResponse:
    """Upload an audio file and stream transcription progress as SSE."""

    suffix = _validate_filename(file.filename)
    tmp_dir = Path(tempfile.gettempdir()) / "whisper_web_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{secrets.token_hex(8)}{suffix}"

    try:
        size = await _save_upload(file, tmp_path)
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    LOG.info("Received upload: %s (%.2f MB) -> %s", file.filename, size / 1e6, tmp_path)

    if service.model is None:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="model not loaded yet")

    interval = max(0, int(timestamp_interval))
    original_name = file.filename

    async def event_stream() -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def push(event: str, data: dict) -> None:
            asyncio.run_coroutine_threadsafe(queue.put((event, data)), loop)

        def worker() -> None:
            try:
                push("status", {"phase": "starting", "message": "Loading audio..."})
                segments, info = service.model.transcribe(
                    str(tmp_path),
                    word_timestamps=False,
                    beam_size=BEAM_SIZE,
                )
                duration = float(getattr(info, "duration", 0.0) or 0.0)
                push(
                    "language",
                    {
                        "language": info.language,
                        "probability": float(info.language_probability),
                        "duration_seconds": duration,
                    },
                )
                push("status", {"phase": "transcribing", "message": "Transcribing audio..."})

                parts: list[str] = []
                last_mark = 0.0
                last_emit = 0.0
                for seg in segments:
                    text = (seg.text or "").strip()
                    if interval > 0 and seg.start >= last_mark + interval:
                        parts.append(f"\n{_format_timestamp(seg.start)}\n")
                        last_mark = seg.start
                    parts.append(text)

                    now = time.monotonic()
                    if duration > 0 and (now - last_emit) > 0.25:
                        percent = min(100.0, max(0.0, (seg.end / duration) * 100.0))
                        push(
                            "progress",
                            {
                                "percent": round(percent, 1),
                                "current_seconds": round(seg.end, 1),
                                "total_seconds": round(duration, 1),
                            },
                        )
                        last_emit = now

                full_text = " ".join(parts).strip()
                push("progress", {"percent": 100.0, "current_seconds": duration, "total_seconds": duration})
                push(
                    "complete",
                    {
                        "text": full_text,
                        "filename": Path(original_name).with_suffix(".txt").name,
                        "language": info.language,
                        "duration_seconds": duration,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                LOG.exception("Transcription failed")
                push("error", {"message": str(exc)})
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        # Run the (sync, GIL-released-during-CUDA) transcription off the event loop.
        loop.run_in_executor(None, worker)

        try:
            while True:
                # Detect client disconnects so we don't keep transcribing into the void.
                if await request.is_disconnected():
                    LOG.info("Client disconnected — abandoning stream")
                    break

                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Heartbeat keeps proxies (Cloudflare) from closing the connection.
                    yield b": keepalive\n\n"
                    continue

                if item is None:
                    break
                event, data = item
                yield _sse(event, data)
        finally:
            tmp_path.unlink(missing_ok=True)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # disables proxy buffering where honored
        "Connection": "keep-alive",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# Mount static assets (JS, CSS, etc.) under /static.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
