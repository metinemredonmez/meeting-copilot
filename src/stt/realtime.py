# src/stt/realtime.py
import os
import time
import asyncio, base64, json, inspect, sys
from asyncio import Queue

# Akan transcript hızını ayarla (ms)
REALTIME_PARTIAL_EMIT_MS = int(os.getenv("REALTIME_PARTIAL_EMIT_MS", "250"))

# Ayarlar
STT_LANG = os.getenv("STT_LANG", "en").lower()      # kaynak konuşma dili (ör. en, tr)
TRANSLATE_TO = (os.getenv("TRANSLATE_TO", "") or "").lower().strip()
REALTIME_ONLY_TEXT = os.getenv("REALTIME_ONLY_TEXT", "1") == "1"
REALTIME_DEBUG = os.getenv("REALTIME_DEBUG", "0") == "1"
FORCE_COMMIT_MS = int(os.getenv("FORCE_COMMIT_MS", "0"))

# websockets sürüm uyumluluğu
try:
    from websockets.asyncio.client import connect as _ws_connect  # type: ignore[attr-defined]
except Exception:
    from websockets.client import connect as _ws_connect          # type: ignore

from ..audio.capture import AudioCapture, CaptureConfig
from ..app_types import TranscriptChunk

REALTIME_URL = os.getenv(
    "OPENAI_REALTIME_URL",
    "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
)
API_KEY = os.getenv("OPENAI_API_KEY", "")

def _connect(url: str, headers: dict, **kw):
    sig = inspect.signature(_ws_connect)
    if "extra_headers" in sig.parameters:
        return _ws_connect(url, extra_headers=headers, **kw)
    else:
        return _ws_connect(url, additional_headers=headers, **kw)

async def stream_text():
    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")

    cfg = CaptureConfig()
    cap = AudioCapture(cfg)
    cap.start()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "OpenAI-Beta": "realtime=v1",
    }

    out_q: Queue[TranscriptChunk] = Queue()
    in_flight = False  # yanıt üretimi devam ediyor mu (transcript yanıtı)

    async with _connect(REALTIME_URL, headers, ping_interval=20) as ws:
        # --- Talimat inşası: verbatim transcript mi, TR çeviri mi? ---
        if TRANSLATE_TO:
            instr = (
                f"You will hear {STT_LANG} speech. Translate it into {TRANSLATE_TO}. "
                "Output ONLY the translation of what was said. "
                "Do not add apologies, prefaces, labels, or extra words."
            )
        else:
            instr = (
                "Transcribe ONLY what you hear. "
                "Return verbatim transcript in the original language. "
                "Do not translate, summarize, apologize, or add words."
            )

        # EN konuşmayı TR'ye çevir (veya verbatim) — yalnız metin dön
        session_payload = {
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.3,
                "silence_duration_ms": 250,
                "create_response": True,      # konuşma bitince otomatik 'response'
                "interrupt_response": True,
                "prefix_padding_ms": 300,
            },
            "input_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "gpt-4o-transcribe",
                "language": STT_LANG
            },
            "instructions": instr,
        }
        if REALTIME_ONLY_TEXT:
            session_payload["modalities"] = ["text"]

        await ws.send(json.dumps({"type": "session.update", "session": session_payload}))
        mode = "translate" if TRANSLATE_TO else "transcribe"
        print(f"[realtime] session updated (server_vad + {mode} + text-only)")

        partial_buf = ""
        last_emit = 0.0

        async def send_audio():
            nonlocal in_flight
            last_commit = time.monotonic()
            sent_since_commit = 0

            async for chunk in cap.frames():
                b64 = base64.b64encode(chunk).decode("utf-8")
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": b64}))
                sent_since_commit += len(chunk)

                # Opsiyonel: zorunlu commit (aba güvencesi)
                if FORCE_COMMIT_MS > 0 and not in_flight:
                    now = time.monotonic()
                    if (now - last_commit) * 1000 >= FORCE_COMMIT_MS and sent_since_commit > 0:
                        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        await ws.send(json.dumps({
                            "type": "response.create",
                            "response": {"modalities": ["text"]}
                        }))
                        last_commit = now
                        sent_since_commit = 0

        async def recv_events():
            nonlocal partial_buf, last_emit, in_flight
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    if REALTIME_DEBUG:
                        print("[realtime][raw]", raw)
                    continue

                t = data.get("type", "")

                if t == "error":
                    print("[realtime][ERROR]", data.get("error") or data)
                    continue

                # transcript yanıtı başlatıldı → kilit
                if t in ("response.created",):
                    in_flight = True

                # Akan metin (çeşitli adlarla gelebilir)
                if t in (
                    "response.text.delta",
                    "response.output_text.delta",
                    "response.delta",
                    "transcript.delta",
                    "response.audio_transcript.delta",
                ):
                    delta = (
                        data.get("delta")
                        or data.get("text")
                        or data.get("output_text")
                        or data.get("transcript")
                        or ""
                    )
                    if delta:
                        partial_buf += delta
                        now = time.monotonic()
                        if (now - last_emit) * 1000 >= REALTIME_PARTIAL_EMIT_MS:
                            await out_q.put(TranscriptChunk(text=partial_buf, is_final=False))
                            last_emit = now
                        if REALTIME_DEBUG:
                            sys.stdout.write("\r[partial] " + partial_buf.replace("\n", " ")[:140] + "   ")
                            sys.stdout.flush()
                    continue

                # Final metin → kilidi bırak
                if t in (
                    "response.text.done",
                    "response.output_text.done",
                    "response.completed",
                    "transcript.completed",
                    "response.output_item.done",
                    "response.done",
                    "response.audio_transcript.done",
                ):
                    text = (
                        data.get("text")
                        or data.get("output_text")
                        or data.get("transcript")
                        or partial_buf
                        or ""
                    ).strip()
                    if text:
                        await out_q.put(TranscriptChunk(text=text, is_final=True))
                    partial_buf = ""
                    last_emit = 0.0
                    in_flight = False
                    continue

                # Sesli event'leri yok say
                if t.startswith("response.audio"):
                    if REALTIME_DEBUG:
                        print(f"[realtime][skip audio event] {t}")
                    continue

                if REALTIME_DEBUG:
                    print(f"[realtime][event] {t}: {data}")

        sender = asyncio.create_task(send_audio())
        receiver = asyncio.create_task(recv_events())

        try:
            while True:
                item = await out_q.get()
                yield item
        finally:
            sender.cancel()
            receiver.cancel()
            cap.stop()
