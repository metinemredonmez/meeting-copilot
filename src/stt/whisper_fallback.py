import asyncio
from typing import AsyncGenerator
from ..audio.capture import AudioCapture, CaptureConfig
from ..app_types import TranscriptChunk

def _transcribe_block(audio_bytes: bytes, sr: int) -> str:
    return ""  # Sprint-2: faster-whisper entegrasyonu

async def stream_text() -> AsyncGenerator[TranscriptChunk, None]:
    cfg = CaptureConfig()
    cap = AudioCapture(cfg)
    cap.start()

    buf = bytearray()
    block_time_sec = max(0.2, cfg.block_ms / 1000.0)
    window_sec = 1.0
    blocks_per_window = int(window_sec / block_time_sec)

    i = 0
    try:
        async for chunk in cap.frames():
            buf.extend(chunk)
            i += 1
            if i % blocks_per_window == 0:
                text = _transcribe_block(bytes(buf), cfg.samplerate)
                buf.clear()
                if text:
                    yield TranscriptChunk(text=text, is_final=True)
    finally:
        cap.stop()
