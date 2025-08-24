# src/hotkey/global_hotkey.py
import os
from pynput import keyboard
import pyperclip
from src.ui.subtitles import get_last_answer  # <<< değişti

def _parse_hotkey(h: str):
    parts = [p.strip().lower() for p in h.split("+")]
    mods = set(p for p in parts[:-1])
    key = parts[-1]
    return mods, key

def start_hotkey():
    hot = os.getenv("HOTKEY", "alt+shift+c")
    mods, key = _parse_hotkey(hot)

    current = set()

    def on_press(k):
        try:
            name = k.name if hasattr(k, "name") else k.char
        except Exception:
            name = str(k)
        name = (name or "").lower()

        if name in ("alt", "alt_l", "alt_r", "cmd", "cmd_l", "cmd_r", "ctrl", "control", "shift"):
            current.add(name.replace("_l","").replace("_r",""))
        elif name:
            # ana tuş
            if key == name and any(m in current for m in ["alt", "cmd", "control", "ctrl"]) and "shift" in current:
                txt = get_last_answer()
                if txt:
                    pyperclip.copy(txt)
        return True

    def on_release(k):
        try:
            name = k.name if hasattr(k, "name") else k.char
        except Exception:
            name = str(k)
        name = (name or "").lower()
        if name in current:
            current.discard(name)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()
