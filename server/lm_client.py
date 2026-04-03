"""
lm_client.py — Клієнт для LM Studio (OpenAI-сумісний локальний LLM).

Архітектура:
- Singleton-клієнт (один на весь процес)
- Lazy ініціалізація моделей при першому запиті
- TTL-кеш для назв моделей (не питаємо /v1/models щоразу)
- Автоматичний вибір chat vs embedding моделі
- Structured logging через вбудований logging модуль
- Graceful fallback якщо LM Studio недоступний
"""

import logging
import math
import hashlib
import time
from functools import cached_property
from typing import Optional

import requests
from openai import OpenAI

log = logging.getLogger(__name__)

# ─── Конфігурація ────────────────────────────────────────────────────────────

LM_STUDIO_URL = "http://127.0.0.1:1234/v1"
REQUEST_TIMEOUT = 3        # сек для запиту до /v1/models
INFERENCE_TIMEOUT = 30     # сек для inference запитів
MODEL_CACHE_TTL = 60       # сек — як часто оновлювати список моделей
EMBEDDING_KEYWORDS = frozenset(["embed", "nomic", "bge", "e5", "minilm", "gte"])
CHAT_KEYWORDS = frozenset(["mistral", "llama", "qwen", "dolphin", "instruct", "chat", "hermes"])

# ─── Internal State ───────────────────────────────────────────────────────────

_openai_client: Optional[OpenAI] = None
_model_cache: dict[str, object] = {}  # { "models": [], "expires_at": float }


def _get_client() -> OpenAI:
    """Singleton OpenAI-клієнт до LM Studio."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            base_url=LM_STUDIO_URL,
            api_key="lm-studio",
            timeout=INFERENCE_TIMEOUT,
        )
        log.debug("LM Studio OpenAI client initialized at %s", LM_STUDIO_URL)
    return _openai_client


def _fetch_models() -> list[dict]:
    """Отримує список моделей з LM Studio з TTL-кешуванням."""
    global _model_cache
    
    now = time.monotonic()
    if _model_cache.get("expires_at", 0) > now:
        return _model_cache["models"]
    
    try:
        resp = requests.get(f"{LM_STUDIO_URL}/models", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        _model_cache = {"models": models, "expires_at": now + MODEL_CACHE_TTL}
        log.debug("Fetched %d models from LM Studio", len(models))
        return models
    except Exception as exc:
        log.warning("Cannot reach LM Studio at %s: %s", LM_STUDIO_URL, exc)
        return _model_cache.get("models", [])


def _select_model(prefer: str) -> str:
    """
    Вибирає найбільш підходящу модель з доступних.
    
    Args:
        prefer: "embed" або "chat"
    Returns:
        ID моделі або пустий рядок якщо жодна не знайдена.
    """
    models = _fetch_models()
    if not models:
        return ""

    keywords = EMBEDDING_KEYWORDS if prefer == "embed" else CHAT_KEYWORDS
    fallback_keywords = CHAT_KEYWORDS if prefer == "embed" else EMBEDDING_KEYWORDS

    # Точний пріоритет: спочатку шукаємо prefered моделі
    for m in models:
        if any(kw in m["id"].lower() for kw in keywords):
            log.debug("Selected %s model: %s", prefer, m["id"])
            return m["id"]

    # Fallback: будь-яка інша модель
    for m in models:
        if any(kw in m["id"].lower() for kw in fallback_keywords):
            log.debug("Fallback to %s model for %s: %s", "other", prefer, m["id"])
            return m["id"]

    # Якщо нічого — перша у списку
    return models[0]["id"]


# ─── Public API ───────────────────────────────────────────────────────────────

def chat(system_prompt: str, user_message: str, temperature: float = 0.3) -> str:
    """
    Синхронний виклик LLM для генерації тексту.
    
    Returns:
        Відповідь моделі. Якщо LM Studio недоступний — повертає порожній рядок,
        НЕ піднімає виключення (щоб API залишалось доступним).
    """
    model = _select_model("chat")
    if not model:
        log.error("No chat model available. Is LM Studio running?")
        return ""

    try:
        response = _get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=1024,
        )
        reply = response.choices[0].message.content.strip()
        log.debug("Chat response (%d chars) via model %s", len(reply), model)
        return reply

    except Exception as exc:
        log.error("LLM inference failed (model=%s): %s", model, exc)
        return ""


def get_embedding(text: str) -> list[float]:
    """
    Отримує dense embedding-вектор для тексту.
    
    Returns:
        Список float. Якщо embedding-сервер недоступний — повертає
        детерміністичний BM25-like хеш-вектор як fallback.
    """
    if not text or not text.strip():
        return _hash_embedding("")

    model = _select_model("embed")
    if not model:
        log.warning("No embedding model found, using hash fallback.")
        return _hash_embedding(text)

    try:
        response = _get_client().embeddings.create(model=model, input=text[:4096])
        vec = response.data[0].embedding
        log.debug("Embedding (%d dims) retrieved for text[:%d]", len(vec), min(len(text), 50))
        return vec

    except Exception as exc:
        log.warning("Embedding failed (model=%s): %s. Using hash fallback.", model, exc)
        return _hash_embedding(text)


def is_available() -> dict:
    """
    Перевірка стану LM Studio — корисно для /health ендпоїнту.
    
    Returns:
        dict з полями: available (bool), chat_model, embed_model, model_count.
    """
    models = _fetch_models()
    return {
        "available": len(models) > 0,
        "model_count": len(models),
        "chat_model": _select_model("chat"),
        "embed_model": _select_model("embed"),
        "server_url": LM_STUDIO_URL,
    }


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _hash_embedding(text: str, dims: int = 256) -> list[float]:
    """
    Детерміністичний fallback embedding через хешування.
    Використовує TF (term frequency) підхід для кращої семантичної схожості, 
    ніж випадкові числа.
    """
    words = text.lower().split()
    vec = [0.0] * dims
    for i, word in enumerate(words[:512]):
        # Два різних хеші для рівномірного розподілу
        h1 = int(hashlib.md5(word.encode()).hexdigest(), 16) % dims
        h2 = int(hashlib.sha1(word.encode()).hexdigest(), 16) % dims
        weight = 1.0 / math.log2(i + 2)  # TF-IDF-like затухання
        vec[h1] += weight
        vec[h2] += weight * 0.5
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]
