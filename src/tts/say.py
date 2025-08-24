import os

def speak(text: str):
    enabled = os.getenv("TTS_ENABLED", "false").lower() == "true"
    if not enabled or not text:
        return
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass
