# src/main.py
import os
import threading
import anyio
from dotenv import load_dotenv
from typing import List

from src.nlu.question_detect import is_question
from src.llm.openai_client import OpenAIClient
from src.ui.subtitles import (
    start_subtitles_main_thread,
    run_subtitles_mainloop_blocking,
    show_subtitle,
    show_answer,
)
from src.hotkey.global_hotkey import start_hotkey
from src.tts.say import speak

load_dotenv(override=True)

def choose_stt():
    backend = os.getenv("STT_BACKEND", "realtime").lower()
    if backend == "realtime":
        from src.stt.realtime import stream_text
        return stream_text
    elif backend == "whisper":
        from src.stt.whisper_fallback import stream_text
        return stream_text
    else:
        raise RuntimeError(f"Unknown STT_BACKEND: {backend}")

async def run_async_worker():
    start_hotkey()
    client = OpenAIClient()

    context_buffer: List[str] = []
    stream_fn = choose_stt()
    stream_iter = stream_fn()

    if not hasattr(stream_iter, "__aiter__"):
        raise TypeError("stream_text() async generator döndürmeli.")

    try:
        async for chunk in stream_iter:
            txt = (chunk.text or "").strip()
            if not txt:
                continue

            # Altyazıyı güncelle
            show_subtitle(txt)
            print(f"[transcript]{' (final)' if chunk.is_final else ''}: {txt}")

            context_buffer.append(txt)
            if len(" ".join(context_buffer)) > 800:
                context_buffer[:] = context_buffer[-5:]

            if chunk.is_final and is_question(txt):
                ctx = " ".join(context_buffer)[-600:]
                lang = "EN"  # kısa cevaplar İngilizce
                reply = await client.short_reply(ctx, txt, lang)
                show_answer(reply, copy_clipboard=True)
                speak(reply)
    except RuntimeError as e:
        print(f"[audio][ERROR] {e}")

def _asyncio_thread():
    anyio.run(run_async_worker)

if __name__ == "__main__":
    # 1) Tk penceresini ANA THREAD'de hazırla
    start_subtitles_main_thread()

    # 2) Asenkron işleri ayrı bir thread'de çalıştır
    t = threading.Thread(target=_asyncio_thread, daemon=True)
    t.start()

    # 3) Ana thread: Tk mainloop (bloklar)
    run_subtitles_mainloop_blocking()
