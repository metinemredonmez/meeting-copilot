# src/stt/whisper_local.py
import os
import asyncio
import numpy as np
from typing import AsyncGenerator
import whisper
from ..audio.capture import AudioCapture, CaptureConfig
from ..app_types import TranscriptChunk

# Whisper modelini yükle (bir kez)
MODEL = None


def load_whisper_model():
    global MODEL
    if MODEL is None:
        model_size = os.getenv("WHISPER_MODEL", "base")  # tiny, base, small, medium, large
        print(f"[whisper] Loading model: {model_size}")
        MODEL = whisper.load_model(model_size)
        print(f"[whisper] Model loaded successfully")
    return MODEL


def transcribe_audio(audio_bytes: bytes, sr: int) -> str:
    """Whisper ile ses->metin"""
    try:
        model = load_whisper_model()

        # bytes -> numpy array
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # Çok kısa ses varsa skip et
        if len(audio_np) < sr * 0.5:  # 0.5 saniyeden kısa
            return ""

        # Whisper transkript et
        result = model.transcribe(
            audio_np,
            language="tr",  # Türkçe
            task="transcribe",
            verbose=False,
            word_timestamps=False,
            fp16=False,  # CPU için
            temperature=0.0,  # Deterministik
            beam_size=5,  # Daha iyi kalite
            best_of=5,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0
        )

        text = result["text"].strip()
        if text and text != "[BLANK_AUDIO]":
            return text
        return ""

    except Exception as e:
        print(f"[whisper][ERROR] {e}")
        return ""


async def stream_text() -> AsyncGenerator[TranscriptChunk, None]:
    """Local Whisper ile streaming transcription"""
    cfg = CaptureConfig()
    cap = AudioCapture(cfg)
    cap._running = True  # Önemli!
    cap.start()

    buf = bytearray()
    chunk_duration = float(os.getenv("WHISPER_CHUNK_DURATION", "2.0"))  # 2 saniye
    bytes_per_chunk = int(cfg.samplerate * chunk_duration * 2)  # int16 = 2 bytes

    print(f"[whisper] Starting with {chunk_duration}s chunks, {bytes_per_chunk} bytes each")

    try:
        async for audio_chunk in cap.frames():
            buf.extend(audio_chunk)

            # Yeterli veri birikince transkript et
            if len(buf) >= bytes_per_chunk:
                audio_bytes = bytes(buf)
                buf.clear()

                print(f"[whisper] Processing {len(audio_bytes)} bytes...")

                # CPU-intensive işlemi executor'da çalıştır
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(
                    None,
                    transcribe_audio,
                    audio_bytes,
                    cfg.samplerate
                )

                if text:
                    print(f"[whisper] Transcript: {text}")
                    yield TranscriptChunk(text=text, is_final=True)
                else:
                    print("[whisper] No speech detected")

    except Exception as e:
        print(f"[whisper][ERROR] {e}")
    finally:
        cap.stop()