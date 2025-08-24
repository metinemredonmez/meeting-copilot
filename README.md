# Meeting Copilot (Python MVP)

## 🎯 Amaç
Zoom / Google Meet / Teams toplantılarında konuşmaları **anlık transkribe edip**, soruları tespit ederek **ChatGPT’den hızlı, kısa ve toplantıya uygun yanıt** üretmek.  
Sonuç: Yanıt ekranda görünecek, panoya kopyalanacak, opsiyonel olarak TTS ile seslendirilebilecek.

---

meeting-copilot/
├─ .gitignore
├─ requirements.txt
├─ .env.example
├─ README.md
├─ src/
│ ├─ main.py # uygulama girişi
│ ├─ config.py # ortam değişkenleri
│ ├─ app_types.py # veri modelleri
│ ├─ audio/
│ │ └─ capture.py # virtual audio/mic'den PCM capture
│ ├─ stt/
│ │ └─ realtime.py # OpenAI Realtime entegrasyonu (stream)
│ ├─ nlu/
│ │ └─ question_detect.py# soru algılama + dil tespiti
│ ├─ llm/
│ │ └─ openai_client.py # ChatGPT kısa yanıt üretimi
│ └─ ui/
│ └─ overlay.py # terminal/clipboard gösterimi
└─ tests/
└─ test_question_detect.py

## 📂 Proje Yapısı


---

## ⚙️ Gereklilikler

- Python 3.10+
- PortAudio (Mac: `brew install portaudio`, Ubuntu: `apt install portaudio19-dev`)
- OpenAI API key (`OPENAI_API_KEY`)

---

## 🚀 Kurulum

```bash
# ortam oluştur
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# bağımlılıkları yükle
pip install -r requirements.txt

# .env ayarla
cp .env.example .env
# → OPENAI_API_KEY=sk-...
# → OPENAI_MODEL=gpt-4o-mini
# → AUDIO_INPUT_DEVICE=BlackHole 2ch (veya VB-Audio)


▶️ Çalıştırma
1. Ses yakalama testi
python -m src.audio.capture --list           # cihazları gör
python -m src.audio.capture --monitor 5      # seviye izle
python -m src.audio.capture --record 5 --out test.wav


2. Mock STT (ilk deneme)
python -m src.main
# terminalde metin yaz → '?' ile bitir → kısa yanıt gelir (clipboard’a kopyalanır)
3. Gerçek zamanlı STT (OpenAI Realtime)

src/stt/realtime.py içindeki iskelet doldurulacak.

Virtual audio cihazından 16kHz PCM → base64 → input_audio_buffer.append.

Her 1 sn’de bir commit + response.create.

Gelen transcript.delta / transcript.completed eventlerinden TranscriptChunk üret.
