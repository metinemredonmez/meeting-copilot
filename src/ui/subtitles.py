# src/ui/subtitles.py
import time
import threading
from typing import Optional

# Tk, ana thread'de başlatılacak (main.py öyle yapıyor)
try:
    import tkinter as tk
except Exception as e:
    tk = None

_root: Optional["tk.Tk"] = None
_subtitle_var: Optional["tk.StringVar"] = None
_answer_var: Optional["tk.StringVar"] = None
_last_answer_text: str = ""
_lock = threading.Lock()

# Otomatik kaybolma süreleri (sn)
SUBTITLE_FADE_SEC = 0          # 0 = sabit kalsın (transkript akacak)
ANSWER_FADE_SEC = 5            # kısa cevap 5 sn sonra kapansın

def _safe_after(ms: int, fn, *args):
    if _root is None:
        return
    try:
        _root.after(ms, fn, *args)
    except Exception:
        pass

def start_subtitles_main_thread():
    """Ana thread'de TK penceresini hazırla (main.py burayı çağırıyor)."""
    global _root, _subtitle_var, _answer_var
    if tk is None:
        print("[ui] Tk yüklenemedi; konsol moduna düşeceğiz.")
        return

    _root = tk.Tk()
    _root.title("Meeting Copilot")
    _root.overrideredirect(True)         # çerçevesiz
    _root.wm_attributes("-topmost", True)
    try:
        _root.wm_attributes("-alpha", 0.96)
    except Exception:
        pass

    # Boyut/konum (sağ-alt köşe)
    w, h = 680, 160
    sw = _root.winfo_screenwidth()
    sh = _root.winfo_screenheight()
    x, y = sw - w - 40, sh - h - 80
    _root.geometry(f"{w}x{h}+{x}+{y}")

    # Arka plan
    frame = tk.Frame(_root, bg="#0f172a")  # slate-900
    frame.pack(fill="both", expand=True)

    # Sürükleme
    start = {"x": 0, "y": 0}
    def _start_move(e):
        start["x"], start["y"] = e.x, e.y
    def _do_move(e):
        if _root:
            _root.geometry(f"+{e.x_root-start['x']}+{e.y_root-start['y']}")
    frame.bind("<Button-1>", _start_move)
    frame.bind("<B1-Motion>", _do_move)

    # Değişkenler
    _subtitle_var = tk.StringVar(value="")
    _answer_var = tk.StringVar(value="")

    # Altyazı (akış)
    lbl_sub = tk.Label(
        frame, textvariable=_subtitle_var,
        fg="#e2e8f0", bg="#0f172a",
        font=("Helvetica", 16), justify="left", wraplength=w-30
    )
    lbl_sub.pack(padx=12, pady=(12, 6), anchor="w")

    # Kısa cevap (belirgin)
    lbl_ans = tk.Label(
        frame, textvariable=_answer_var,
        fg="#10b981", bg="#0f172a",  # emerald-500
        font=("Helvetica", 16, "bold"), justify="left", wraplength=w-30
    )
    lbl_ans.pack(padx=12, pady=(0, 10), anchor="w")

def run_subtitles_mainloop_blocking():
    """Ana thread'de bloklayan mainloop (main.py burayı çağırıyor)."""
    if _root is None:
        # Tk yoksa konsol modunda sadece beklemeyelim
        print("[ui] Tk devre dışı; mainloop yok.")
        while True:
            time.sleep(1)
    _root.mainloop()

def show_subtitle(text: str):
    """Altyazı (partial/final transcript) – her thread'den güvenli."""
    if not text:
        return
    if _root is None:
        # Tk yoksa konsola yaz
        print(f"[subtitle] {text}")
        return
    def _upd():
        if _subtitle_var is not None:
            _subtitle_var.set(text)
    _safe_after(0, _upd)

    if SUBTITLE_FADE_SEC > 0:
        def _clear():
            if _subtitle_var is not None:
                _subtitle_var.set("")
        _safe_after(int(SUBTITLE_FADE_SEC * 1000), _clear)

def show_answer(text: str, copy_clipboard: bool = True):
    """Final sonrası kısa yanıt (sadece soruysa çağrılır)."""
    global _last_answer_text
    if not text:
        return
    with _lock:
        _last_answer_text = text

    if _root is None:
        print(f"[answer] {text}")
        return

    try:
        if copy_clipboard:
            import pyperclip
            pyperclip.copy(text)
    except Exception:
        pass

    def _upd():
        if _answer_var is not None:
            _answer_var.set(text)
    _safe_after(0, _upd)

    def _clear():
        if _answer_var is not None:
            _answer_var.set("")
    _safe_after(int(ANSWER_FADE_SEC * 1000), _clear)

def get_last_answer() -> str:
    with _lock:
        return _last_answer_text
