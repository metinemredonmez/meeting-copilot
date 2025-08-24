# src/llm/openai_client.py
import os
import json
import http.client


class OpenAIClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY missing")

    async def short_reply(self, context: str, question: str, lang: str) -> str:
        system = (
            "You are a live meeting copilot.\n"
            "- You receive Turkish context/questions (translated from English speech)\n"
            "- Translate the Turkish question back to English, then answer it\n"
            "- ALWAYS respond in ENGLISH\n"
            "- Keep it to 1–2 sentences, suitable to speak aloud\n"
            "- Be polite and concise. Avoid new commitments unless approved\n"
            "- If uncertain, say so briefly in English"
        )

        user = (
            f"Turkish context (from English speech): {context}\n"
            f"Turkish question (from English speech): {question}\n\n"
            f"Please:\n"
            f"1. Understand what the original English question was\n"
            f"2. Answer that question in English\n"
            f"3. Keep response short for speaking aloud"
        )

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 150,
            "temperature": 0.7
        }

        conn = http.client.HTTPSConnection("api.openai.com")
        try:
            conn.request(
                "POST", "/v1/chat/completions",
                body=json.dumps(body),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")

            if resp.status != 200:
                print(f"[OpenAI API Error] Status: {resp.status}, Response: {data}")
                return "Sorry, I couldn't process that request."  # İngilizce hata mesajı

        finally:
            conn.close()

        try:
            payload = json.loads(data)
            choices = payload.get("choices", [])
            if choices and "message" in choices[0]:
                text = choices[0]["message"].get("content", "")
                return text.strip()
        except json.JSONDecodeError as e:
            print(f"[JSON Error] {e}, Raw data: {data}")

        return "Sorry, I couldn't understand that."  # İngilizce hata mesajı