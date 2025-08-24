# src/nlu/question_detect.py
import os

# Türkçe soru kalıpları (çünkü transcript Türkçe gelecek)
TR_QUESTION_PATTERNS = [
    " mı", " mi", " mu", " mü", " mısın", " misin", " misiniz",
    " olur mu", " olabilir mi", " anlatır mısınız", " nedir", " nasıl", " ne zaman",
    "ne", "neden", "nasıl", "kim", "nerede", "ne zaman", "hangi", "kaç"
]


def is_question(txt: str) -> bool:
    """Türkçe metinde soru var mı kontrol et (çünkü transcript Türkçe)"""
    t = (txt or "").strip().lower()
    if not t:
        return False

    # Soru işareti varsa kesin soru
    if t.endswith("?"):
        return True

    # Türkçe soru kalıpları
    return any(pattern in t for pattern in TR_QUESTION_PATTERNS)


def decide_lang(context: str, question: str = "") -> str:
    """AI yanıtı için dil - her zaman İngilizce"""
    force_lang = os.getenv("FORCE_LANG", "").strip().lower()
    if force_lang == "en":
        return "EN"
    elif force_lang == "tr":
        return "TR"

    # Default: AI yanıtı İngilizce
    return "EN"