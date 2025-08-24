# src/api/server.py
import os
import asyncio
import json
from typing import Set
from pathlib import Path

import sounddevice as sd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# ── .env'i proje kökünden yükle ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]   # .../meeting-copilot/
load_dotenv(dotenv_path=ROOT / ".env", override=True)

# Realtime akış fonksiyonun
from src.stt.realtime import stream_text as realtime_stream

app = FastAPI(title="Meeting Copilot Backend")

# ── Global durum ───────────────────────────────────────────────────────────────
_subs: Set[WebSocket] = set()
_runner: asyncio.Task | None = None
_stop_evt = asyncio.Event()

# ── Modeller ──────────────────────────────────────────────────────────────────
class StartReq(BaseModel):
    device: str | None = None          # "BlackHole 2ch" vb.
    lang: str | None = None            # örn. "en"
    translate_to: str | None = None    # örn. "tr"

class AskReq(BaseModel):
    question: str | None = None
    context_en: str | None = None
    context_tr: str | None = None
    target: str | None = "en"          # cevap dili (demo)

# ── Yardımcılar ───────────────────────────────────────────────────────────────
def _set_env_from_start(req: StartReq) -> None:
    if req.device:
        os.environ["AUDIO_INPUT_DEVICE"] = req.device
    if req.lang:
        os.environ["STT_LANG"] = req.lang
    if req.translate_to:
        # EN -> TR canlı çeviri için asgari env
        os.environ["REALTIME_ONLY_TEXT"] = "1"
        os.environ["STT_LANG"] = "en"
        os.environ["REALTIME_PARTIAL_EMIT_MS"] = "200"

def _has_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))

async def _broadcast(msg: dict) -> None:
    payload = json.dumps(msg, ensure_ascii=False)
    dead = []
    for s in list(_subs):
        try:
            await s.send_text(payload)
        except Exception:
            dead.append(s)
    for s in dead:
        _subs.discard(s)

async def _run_pipeline():
    # Anahtar yoksa kullanıcıya bildirip çık
    if not _has_api_key():
        await _broadcast({"type": "error", "text": "OPENAI_API_KEY missing"})
        return

    backoff = 1
    while not _stop_evt.is_set():
        try:
            async for chunk in realtime_stream():
                await _broadcast({
                    "type": "final" if getattr(chunk, "is_final", False) else "partial",
                    "text": getattr(chunk, "text", "") or "",
                })
                if _stop_evt.is_set():
                    break
            break  # generator normal bitti
        except Exception as e:
            msg = str(e)
            await _broadcast({"type": "error", "text": msg})
            if "session_expired" in msg or "maximum duration of 30 minutes" in msg:
                await _broadcast({"type": "info", "text": "restarting_session"})
                continue
            await asyncio.sleep(min(backoff, 10))
            backoff = min(backoff * 2, 10)

    await _broadcast({"type": "info", "text": "pipeline_stopped"})

# ── HTTP API ──────────────────────────────────────────────────────────────────
@app.get("/status")
async def status():
    return {"running": _runner is not None and not _runner.done(),
            "subscribers": len(_subs)}

@app.get("/devices")
async def devices():
    res = []
    for i, d in enumerate(sd.query_devices()):
        try:
            if int(d.get("max_input_channels", 0)) > 0:
                res.append({"index": i, "name": d["name"]})
        except Exception:
            pass
    return res

@app.post("/start")
async def start(req: StartReq):
    global _runner, _stop_evt
    if _runner and not _runner.done():
        return JSONResponse({"ok": True, "already": True})

    if not _has_api_key():
        return JSONResponse({"ok": False, "error": "OPENAI_API_KEY missing"}, status_code=400)

    _set_env_from_start(req)
    _stop_evt = asyncio.Event()
    _runner = asyncio.create_task(_run_pipeline())
    return {"ok": True}

@app.post("/stop")
async def stop():
    global _runner
    if _runner and not _runner.done():
        _stop_evt.set()
        try:
            await _runner
        finally:
            _runner = None
    return {"ok": True}

@app.get("/diag")
def diag():
    return {
        "has_key": _has_api_key(),
        "model": os.getenv("OPENAI_MODEL"),
        "realtime_url": os.getenv("OPENAI_REALTIME_URL"),
        "audio_device": os.getenv("AUDIO_INPUT_DEVICE"),
    }

@app.post("/ask")
async def ask(req: AskReq):
    q = (req.question or "").strip()
    return {"answer": f"(demo) Answer to: {q}"}

# ── WebSocket (tek tanım) ─────────────────────────────────────────────────────
@app.websocket("/ws/transcript")
async def ws_transcript(ws: WebSocket):
    await ws.accept()
    _subs.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "info", "text": "connected"}))
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    finally:
        _subs.discard(ws)
