import os
import queue
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

import numpy as np
import sounddevice as sd
import asyncio

# ---- Ayarlanabilir parametreler (dotenv ile de verebilirsin) ----
STALL_SECONDS = float(os.getenv("AUDIO_STALL_SECONDS", "1.5"))   # Kaç sn sessizlikte restart
QUEUE_MAX     = int(os.getenv("AUDIO_QUEUE_MAX", "200"))         # Callback->consumer tampon
REOPEN_BACKOFF_MAX = float(os.getenv("AUDIO_REOPEN_BACKOFF_MAX", "3.0"))  # sn

@dataclass
class CaptureConfig:
    device_name: Optional[str] = os.getenv("AUDIO_INPUT_DEVICE") or None
    samplerate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "24000"))  # Realtime için 24kHz
    channels: int = 1
    block_ms: int = int(os.getenv("AUDIO_BLOCK_MS", "50"))  # Daha büyük blok
    dtype: str = "int16"
    _frames_per_block: int = 0  # Alt çizgi ekleyin

    def __post_init__(self):
        self._frames_per_block = max(1, int(self.samplerate * self.block_ms / 1000))

class AudioCapture:
    def __init__(self, cfg: CaptureConfig):
        self.cfg = cfg
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=QUEUE_MAX)
        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._device_index: Optional[int] = None
        self._last_put = time.monotonic()
        self._reopen_backoff = 0.1  # artan gecikme (maks REOPEN_BACKOFF_MAX)

    # ---- Cihaz adından index çöz ----
    def _resolve_device(self, name: Optional[str]) -> Optional[int]:
        devs = sd.query_devices()
        candidates = [(i, d) for i, d in enumerate(devs) if int(d.get("max_input_channels", 0)) > 0]
        if not name or name.strip().lower() in ("", "default", "auto"):
            return None  # default input
        name = name.strip()
        if name.startswith("#") and name[1:].isdigit():
            return int(name[1:])
        lname = name.lower()
        # tam eşleşme
        for i, d in candidates:
            if str(d.get("name", "")).lower() == lname:
                return i
        # kısmi eşleşme
        for i, d in candidates:
            if lname in str(d.get("name", "")).lower():
                return i
        return None

    def _make_stream(self) -> sd.InputStream:
        return sd.InputStream(
            device=self._device_index,
            channels=self.cfg.channels,
            samplerate=self.cfg.samplerate,
            dtype=self.cfg.dtype,
            blocksize=self.cfg._frames_per_block,
            latency="low",
            callback=self._callback,
            dither_off=True,
        )

    def start(self):
        self._device_index = self._resolve_device(self.cfg.device_name)
        if self.cfg.device_name and self._device_index is None:
            names = [f"#{i} {d['name']}" for i, d in enumerate(sd.query_devices())
                     if int(d.get('max_input_channels', 0)) > 0]
            raise RuntimeError(
                f"Input device not found: {self.cfg.device_name}\n"
                f"Available inputs:\n  - " + "\n  - ".join(names) +
                "\nTip: Use exact name, a substring (e.g. 'blackhole'), or '#index'."
            )
        self._open_stream(initial=True)

    def _open_stream(self, initial=False):
        self._stream = self._make_stream()
        self._stream.start()
        self._last_put = time.monotonic()
        self._reopen_backoff = 0.1
        print(f"[audio] {'started' if initial else 'reopened'} device="
              f"{self.cfg.device_name or '(default)'} idx={self._device_index} "
              f"sr={self.cfg.samplerate}Hz ch={self.cfg.channels} block={self.cfg.block_ms}ms")

    def _close_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _restart_stream(self, re_resolve_device: bool = False):
        # isteğe bağlı: cihaz indexini tekrar çöz (index değişmiş olabilir)
        if re_resolve_device:
            self._device_index = self._resolve_device(self.cfg.device_name)
        self._close_stream()
        try:
            self._open_stream(initial=False)
            print("[audio] stream restarted after stall")
        except Exception as e:
            print(f"[audio][ERROR] restart failed: {e}")
            # artan gecikme ile tekrar dene
            time.sleep(self._reopen_backoff)
            self._reopen_backoff = min(REOPEN_BACKOFF_MAX, self._reopen_backoff * 2.0)

    def _callback(self, indata, frames, time_info, status):
        if status:  # overflow/underflow vs.
            print(f"[audio][status] {status!s}")
        # mono mix
        if indata.ndim == 2 and indata.shape[1] > 1:
            x = indata.astype(np.int32).mean(axis=1).astype(np.int16)
        else:
            x = indata.reshape(-1).astype(np.int16)
        try:
            self._q.put_nowait(x.copy())
            self._last_put = time.monotonic()
        except queue.Full:
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait(x.copy())
                self._last_put = time.monotonic()
            except queue.Empty:
                pass

    async def frames(self) -> AsyncGenerator[bytes, None]:
        loop = asyncio.get_event_loop()
        consecutive_stalls = 0
        while self._running:
            stalled = (time.monotonic() - self._last_put) > STALL_SECONDS
            if stalled:
                consecutive_stalls += 1
                # 1. stall: normal restart; 2.+ stall: cihazı da tekrar çöz
                self._restart_stream(re_resolve_device=(consecutive_stalls >= 2))
                await asyncio.sleep(0.01)
                continue
            else:
                consecutive_stalls = 0

            try:
                arr = await loop.run_in_executor(None, self._q.get, True, 0.5)
                yield arr.tobytes()
            except Exception:
                # timeout: döngü başına dön → stall kontrolü tekrar yapılır
                continue

    def stop(self):
        self._running = False
        self._close_stream()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--monitor", type=int, default=0)
    args = parser.parse_args()

    if args.list:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                print(f"[{i}] {d['name']}  (inputs:{d['max_input_channels']})")
        raise SystemExit(0)

    if args.monitor > 0:
        cfg = CaptureConfig()
        cap = AudioCapture(cfg)
        cap._running = True
        cap.start()
        t0 = time.time()
        try:
            while time.time() - t0 < args.monitor:
                try:
                    arr = cap._q.get(timeout=0.2)
                    rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))
                    print(f"RMS: {rms:.1f}")
                except queue.Empty:
                    print("RMS: (yok)")
        finally:
            cap.stop()
