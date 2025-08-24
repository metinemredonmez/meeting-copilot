from pydantic import BaseModel

class TranscriptChunk(BaseModel):
    text: str
    is_final: bool = False

class LLMReply(BaseModel):
    text: str
