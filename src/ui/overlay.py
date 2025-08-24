import os
import threading
import time
import pyperclip
from rich.console import Console
from rich.panel import Panel

console = Console()  # Yıldız işaretleri kaldırıldı
last_text_value = ""  # Global değişken adı düzeltildi
overlay_thread = None


def show_reply_console(text: str):
    if not text:
        return
    pyperclip.copy(text)
    console.print(Panel.fit(text, title="Suggested reply (copied)", border_style="green"))


def tk_overlay_worker(text: str):  # Fonksiyon adı düzeltildi
    import tkinter as tk
    root = tk.Tk()
    root.title("Copilot")
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)
    try:
        root.wm_attributes("-alpha", 0.92)
    except Exception:
        pass

    w, h = 540, 140
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x, y = screen_w - w - 40, screen_h - h - 80
    root.geometry(f"{w}x{h}+{x}+{y}")

    frame = tk.Frame(root, bg="#0f172a")
    frame.pack(fill="both", expand=True)

    lbl = tk.Label(frame, text=text, fg="#e2e8f0", bg="#0f172a",
                   font=("Helvetica", 14), justify="left", wraplength=w - 30)
    lbl.pack(padx=12, pady=12, anchor="w")

    start = {"x": 0, "y": 0}

    def start_move(e):
        start["x"], start["y"] = e.x, e.y

    def do_move(e):
        root.geometry(f"+{e.x_root - start['x']}+{e.y_root - start['y']}")

    frame.bind("<Button-1>", start_move)
    frame.bind("<B1-Motion>", do_move)

    def auto_close():
        time.sleep(5)
        try:
            root.destroy()
        except Exception:
            pass

    threading.Thread(target=auto_close, daemon=True).start()
    root.mainloop()


def show_reply(text: str):
    if not text:
        return

    global last_text_value, overlay_thread
    last_text_value = text
    pyperclip.copy(text)

    backend = os.getenv("OVERLAY_BACKEND", "tk").lower()
    if backend == "tk":
        t = threading.Thread(target=tk_overlay_worker, args=(text,), daemon=True)
        t.start()
        overlay_thread = t
    else:
        show_reply_console(text)


def last_text() -> str:
    return last_text_value