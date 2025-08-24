import os
from dataclasses import dataclass

@dataclass
class Settings:
    openai_api_key: str
    openai_model: str
    realtime_url: str
    sample_rate: int

def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        realtime_url=os.getenv("OPENAI_REALTIME_URL",
                               "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"),
        sample_rate=int(os.getenv("AUDIO_SAMPLE_RATE", "24000")),
    )
