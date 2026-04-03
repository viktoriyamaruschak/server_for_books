import json
import math
import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path

# --- КОНФІГУРАЦІЯ ---
BOOKS_FILE = Path(__file__).parent / "sample_books.json"
LM_STUDIO_URL = "http://127.0.0.1:1234/v1"

# --- ШІ КЛІЄНТ (LM STUDIO) ---
class AIClient:
    """Простий клієнт для спілкування з локальним LM Studio"""
    
    @staticmethod
    def get_models():
        try:
            resp = requests.get(f"{LM_STUDIO_URL}/models", timeout=3)
            return resp.json().get("data", [])
        except:
            return []

    @staticmethod
    def pick_embedding_model():
        """Знаходить спеціальну модель для ембеддінгів (наприклад nomic-embed)"""
        models = AIClient.get_models()
        for m in models:
            mid = m["id"].lower()
            if "embed" in mid or "nomic" in mid:
                return m["id"]
        # Якщо немає спеціальної, беремо першу-ліпшу
        return models[0]["id"] if models else "local-model"

    @staticmethod
    def pick_chat_model():
        """Знаходить чат-модель (Dolphin, Mistral, Llama)"""
        models = AIClient.get_models()
        for m in models:
            mid = m["id"].lower()
            if any(kw in mid for kw in ["mistral", "llama", "qwen", "dolphin", "instruct"]):
                return m["id"]
        return models[0]["id"] if models else "local-model"

    @staticmethod
    def chat(prompt: str, user_msg: str) -> str:
        """Виклик чат-моделі для аналізу тексту"""
        model = AIClient.pick_chat_model()
        try:
            resp = requests.post(
                f"{LM_STUDIO_URL}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_msg}
                    ],
                    "temperature": 0.1
                },
                timeout=20
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Помилка чату ШІ: {e}")
        return user_msg # Fallback: повертаємо оригінал

    @staticmethod
    def get_embedding(text: str) -> list[float]:
        """Отримує векторне представлення тексту (для семантичного пошуку)"""
        if not text.strip():
            return []
            
        model = AIClient.pick_embedding_model()
        try:
            resp = requests.post(
                f"{LM_STUDIO_URL}/embeddings",
                json={"input": text[:2000], "model": model},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()["data"][0]["embedding"]
        except Exception as e:
            print(f"Помилка створення вектора: {e}")
        
        # Fallback якщо ШІ не працює — простий хеш
        return AIClient._fallback_embedding(text)

    @staticmethod
    def _fallback_embedding(text: str) -> list[float]:
        """Якщо LM Studio ліг, робимо фейковий вектор щоб програма не впала"""
        import hashlib
        vec = [0.0] * 128
        for i, word in enumerate(text.lower().split()[:128]):
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % 128
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


# --- ЛОГІКА КНИГ ТА ВЕКТОРІВ ---
def load_books() -> list[dict]:
    try:
        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(x * y for x, y in zip(v1, v2))
    norm = math.sqrt(sum(x * x for x in v1)) * math.sqrt(sum(y * y for y in v2))
    return dot / norm if norm > 0 else 0.0

# Кеш в пам'яті: { book_id: vector }
VECTOR_CACHE = {}

def get_book_vector(book: dict) -> list[float]:
    """Генерує вектор опису книги. КЕШУЄТЬСЯ для швидкості."""
    bid = str(book.get("id"))
    if bid not in VECTOR_CACHE:
        text = f"{book.get('title', '')}. {book.get('description', '')}"
        VECTOR_CACHE[bid] = AIClient.get_embedding(text)
    return VECTOR_CACHE[bid]


# --- FASTAPI ДОДАТОК ---
app = FastAPI(title="AI Book Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchQuery(BaseModel):
    query: str
    limit: int = 5

class SimilarQuery(BaseModel):
    book_title: str
    limit: int = 5

@app.get("/")
def home():
    return {"status": "ok", "message": "Сервер працює! Перейди на /docs для тестування."}

@app.get("/api/books")
def get_all_books():
    """Отримати всі 100 книг"""
    return {"books": load_books()}

@app.get("/api/book/{book_id}")
def get_book_details(book_id: str):
    books = load_books()
    book = next((b for b in books if str(b.get("id")) == book_id), None)
    if not book:
        raise HTTPException(status_code=404, detail="Книгу не знайдено")
    return book

@app.post("/api/search")
def search_similar_books(request: SearchQuery):
    """
    ФІЧА 1: Інтелектуальний пошук природною мовою.
    Нейронка розшифровує запит користувача перед пошуком.
    """
    query = request.query
    if not query or len(query) < 3:
        raise HTTPException(status_code=400, detail="Запит занадто короткий")

    # ЕТАП 1: Точний переклад українського запиту на англійську
    translation_prompt = (
        "Translate the following user query to English accurately. "
        "Return ONLY the English translation, no other text, no quotes."
    )
    english_query = AIClient.chat(translation_prompt, query).strip()
    print(f"DEBUG SEARCH: Translated '{query}' -> '{english_query}'")

    # ЕТАП 2: Розширення англійського запиту для точного пошуку
    analysis_prompt = (
        "You are a professional literary analyst. "
        "Expand the following English search query into a detailed semantic search context for books. "
        "Focus on: primary genre, typical tropes, mood, and central themes. "
        "Response should be a single coherent description (max 2 sentences). No chatter."
    )
    enriched_query = AIClient.chat(analysis_prompt, english_query).strip()
    print(f"DEBUG SEARCH: AI interpreted as: '{enriched_query}'")

    books = load_books()
    query_vector = AIClient.get_embedding(enriched_query)
    
    results = []
    for book in books:
        book_vector = get_book_vector(book)
        score = cosine_similarity(query_vector, book_vector)
        results.append({"relevance": round(score, 4), "book": book})

    results.sort(key=lambda x: x["relevance"], reverse=True)
    return {"original_query": query, "ai_interpreted": enriched_query, "results": results[:request.limit]}

@app.get("/api/book/{book_id}/profile")
def get_book_profile(book_id: str):
    """
    ФІЧА 2: Автоматична генерація сюжетного профілю.
    Виділяє ключові сюжетні лінії та архетипи персонажів.
    """
    books = load_books()
    book = next((b for b in books if str(b.get("id")) == book_id), None)
    if not book:
        raise HTTPException(status_code=404, detail="Книгу не знайдено")

    prompt = (
        f"Analyze the following book: {book['title']}. Description: {book['description']}. "
        "Produce a deep narrative profile in JSON format (strictly JSON, no markdown). "
        "Fields: 'plot_lines' (list), 'archetypes' (list of roles like Hero/Mentor), 'themes' (list), 'mood' (string)."
    )
    
    raw_profile = AIClient.chat("You respond only in strictly valid JSON.", prompt)
    try:
        # Спробуємо розпарсити JSON від нейронки
        import json as pyjson
        return {"book": book, "analysis": pyjson.loads(raw_profile)}
    except:
        return {"book": book, "raw_analysis": raw_profile}

@app.post("/api/similar")
def find_similar_by_title(request: SimilarQuery):
    """
    ФІЧА 3: Контекстне порівняння.
    Знаходить аналоги за структурою сюжету, а не за автором/жанром.
    """
    books = load_books()
    # Шукаємо книгу-джерело
    source = next((b for b in books if b["title"].lower() == request.book_title.lower()), None)
    
    if not source:
        # Якщо книги немає в базі, просто робимо семантичний пошук за назвою як за запитом
        log_msg = f"Книга '{request.book_title}' не знайдена в базі. Виконуємо загальний семантичний пошук."
        print(log_msg)
        return {"message": log_msg, "results": search_similar_books(SearchQuery(query=request.book_title, limit=request.limit))}

    source_id = str(source["id"])
    source_vector = get_book_vector(source)
    
    results = []
    for book in books:
        if str(book.get("id")) == source_id: continue
        book_vector = get_book_vector(book)
        score = cosine_similarity(source_vector, book_vector)
        results.append({"relevance": round(score, 4), "book": book})

    results.sort(key=lambda x: x["relevance"], reverse=True)
    return {"source_book": source, "results": results[:request.limit]}

# Кеш для схожих книг за ID
similar_books_cache = {}

@app.get("/api/book/{book_id}/similar")
def get_similar_by_id(book_id: str, limit: int = 5):
    """
    ФІЧА 4: Схожі за вайбом книги (за ID).
    Вбудоване кешування результатів для миттєвої віддачі на сторінці книги.
    """
    cache_key = f"{book_id}_{limit}"
    if cache_key in similar_books_cache:
        print(f"DEBUG CACHE: Повертаємо схожі книги для {book_id} з кешу")
        return similar_books_cache[cache_key]

    books = load_books()
    source = next((b for b in books if str(b.get("id")) == book_id), None)
    
    if not source:
        raise HTTPException(status_code=404, detail="Книгу не знайдено")

    source_vector = get_book_vector(source)
    
    results = []
    for book in books:
        if str(book.get("id")) == book_id: continue
        book_vector = get_book_vector(book)
        score = cosine_similarity(source_vector, book_vector)
        results.append({"relevance": round(score, 4), "book": book})

    results.sort(key=lambda x: x["relevance"], reverse=True)
    response_data = {"source_book": source, "results": results[:limit]}
    
    # Зберігаємо в кеш
    similar_books_cache[cache_key] = response_data
    return response_data

# Кеш для перекладівписів
translation_cache = {}

@app.get("/api/book/{book_id}/description/uk")
def get_book_description_uk(book_id: str):
    """
    ФІЧА 5: Локалізація описів.
    Перекладає англійський опис книги на українську мову за допомогою ШІ та кешує результат.
    """
    if book_id in translation_cache:
        print(f"DEBUG CACHE: Повертаємо переклад для {book_id} з кешу")
        return {"book_id": book_id, "description_uk": translation_cache[book_id]}

    books = load_books()
    book = next((b for b in books if str(b.get("id")) == book_id), None)
    
    if not book:
        raise HTTPException(status_code=404, detail="Книгу не знайдено")

    original_desc = book.get("description", "")
    if not original_desc:
        return {"book_id": book_id, "description_uk": "Опис відсутній."}

    translation_prompt = (
        "You are a professional literary translator. "
        "Translate the following book description into eloquent Ukrainian. "
        "Return ONLY the Ukrainian translation natively. No other text, no quotes."
    )
    
    translated_desc = AIClient.chat(translation_prompt, original_desc).strip()
    
    # Кешуємо переклад
    translation_cache[book_id] = translated_desc
    return {"book_id": book_id, "description_uk": translated_desc}

