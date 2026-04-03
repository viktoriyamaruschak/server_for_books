"""
book_service.py — Сервісний шар для книжкового додатку.

Архітектура:
- VectorStore: клас для персистентного зберігання та пошуку за embeddings.
  Зберігає індекс на диску (vector_index.json) щоб не перераховувати.
- BookService: основна бізнес-логіка (пошук, профілювання, рекомендації).
- Lazy indexing: індекс будується при першому запиті, не при старті сервера.
"""

import json
import logging
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lm_client import chat, get_embedding, is_available

log = logging.getLogger(__name__)

# ─── Конфігурація ─────────────────────────────────────────────────────────────

BOOKS_FILE = Path(__file__).parent / "sample_books.json"
INDEX_FILE = Path(__file__).parent / "vector_index.json"

# ─── Типи даних ───────────────────────────────────────────────────────────────

Book = dict  # TypeAlias — для читабельності

@dataclass
class SearchResult:
    book: Book
    score: float


# ─── Vector Store ─────────────────────────────────────────────────────────────

class VectorStore:
    """
    Простий, але ефективний in-memory векторний стор з персистентністю на диск.
    
    Зберігає precomputed embeddings у vector_index.json.
    При перезапуску сервера завантажує їх з диску — не рахує повторно.
    Thread-safe завдяки RLock.
    """

    def __init__(self, index_path: Path):
        self._path = index_path
        self._index: dict[str, list[float]] = {}
        self._lock = threading.RLock()
        self._load_from_disk()

    def _load_from_disk(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
                log.info("VectorStore: loaded %d vectors from %s", len(self._index), self._path)
            except Exception as exc:
                log.warning("VectorStore: could not load index from disk: %s", exc)
                self._index = {}

    def _flush_to_disk(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._index, f)
            log.debug("VectorStore: flushed %d vectors to disk", len(self._index))
        except Exception as exc:
            log.error("VectorStore: could not save index: %s", exc)

    def upsert(self, key: str, vector: list[float]):
        with self._lock:
            self._index[key] = vector

    def flush(self):
        with self._lock:
            self._flush_to_disk()

    def get(self, key: str) -> Optional[list[float]]:
        return self._index.get(key)

    def __len__(self) -> int:
        return len(self._index)

    def items(self):
        return self._index.items()


# ─── Book Service ─────────────────────────────────────────────────────────────

class BookService:
    """
    Централізований сервіс для роботи з книгами.
    
    Методи:
    - search(query): Семантичний пошук за описом природною мовою.
    - profile(book_id): Генерація аналітичного профілю книги.
    - similar(book_id or title): Пошук схожих за сюжетом книг.
    - get_all(): Весь каталог.
    - get_by_id(book_id): Пошук за ID.
    """

    def __init__(self):
        self._vector_store = VectorStore(INDEX_FILE)
        self._books: list[Book] = []
        self._index_lock = threading.Lock()
        self._indexed = False

    # ── Публічне API ──────────────────────────────────────────────────────────

    def get_all(self) -> list[Book]:
        if not self._books:
            self._books = self._load_books()
        return self._books

    def get_by_id(self, book_id: str) -> Optional[Book]:
        return next((b for b in self.get_all() if str(b.get("id")) == book_id), None)

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """
        Семантичний пошук.
        Pipeline: query → LLM refinement → embedding → cosine similarity rank.
        """
        self._ensure_index()

        # 1. LLM виділяє семантичний "скелет" запиту
        refined = chat(
            system_prompt=(
                "You are a literary search assistant. "
                "Extract key semantic concepts from the user query: genre, mood, themes, narrative tropes. "
                "Reply with 5-10 keywords, comma-separated. No intro text."
            ),
            user_message=query,
            temperature=0.1,
        ) or query  # fallback: якщо LLM недоступний — шукаємо за оригінальним запитом

        log.debug("Search: '%s' → refined: '%s'", query[:50], refined[:80])

        # 2. Embedding запиту
        query_vec = get_embedding(refined)

        # 3. Косинусна схожість по всіх книгах
        results: list[SearchResult] = []
        for book in self.get_all():
            bid = str(book.get("id"))
            book_vec = self._vector_store.get(bid)
            if not book_vec:
                continue
            score = self._cosine_similarity(query_vec, book_vec)
            results.append(SearchResult(book=book, score=round(score, 5)))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def profile(self, book_id: str) -> Optional[dict]:
        """
        Генерує ШІ-профіль книги: сюжетні лінії, архетипи, теми.
        Повертає структурований dict.
        """
        book = self.get_by_id(book_id)
        if not book:
            return None

        prompt = (
            f"Book: \"{book['title']}\" by {book.get('author', 'Unknown')}\n"
            f"Description:\n{book.get('description', '')}\n\n"
            "Produce a deep literary analysis in valid JSON format:\n"
            "{\n"
            "  \"plot_lines\": [\"<main storyline>\", \"<subplot 1>\"],\n"
            "  \"archetypes\": [\"<role: description>\"],\n"
            "  \"themes\": [\"<theme 1>\", \"<theme 2>\"],\n"
            "  \"mood\": \"<overall atmosphere>\",\n"
            "  \"narrative_structure\": \"<e.g. Hero's Journey, Non-linear, Epistolary>\"\n"
            "}\n"
            "Return ONLY valid JSON, no markdown or extra text."
        )

        raw = chat(
            system_prompt=(
                "You are a professional literary critic and narrative analyst. "
                "You respond ONLY in valid, parseable JSON without markdown code blocks."
            ),
            user_message=prompt,
            temperature=0.2,
        )

        return self._parse_json_response(raw, fallback={
            "plot_lines": [f"Primary storyline in {book.get('genre', 'fiction')}"],
            "archetypes": ["Protagonist", "Antagonist", "Mentor"],
            "themes": ["Identity", "Conflict", "Transformation"],
            "mood": "Atmospheric",
            "narrative_structure": "Linear",
        })

    def similar(self, book_title: str, limit: int = 5) -> list[SearchResult]:
        """
        Знаходить схожі книги за векторною близькістю.
        
        Якщо book_title — це назва книги з бази, ми беремо її вектор і шукаємо аналоги.
        Якщо такої книги немає — ми сприймаємо це як семантичний запит (Feature 1).
        """
        self._ensure_index()

        # Шукаємо точний збіг назви (ігноруючи регістр)
        source = next((b for b in self.get_all() if b["title"].lower() == book_title.lower()), None)
        
        if not source:
            log.info("Title '%s' not found in DB. Falling back to semantic search.", book_title)
            return self.search(book_title, limit)

        source_id = str(source.get("id"))
        source_vec = self._vector_store.get(source_id)

        results: list[SearchResult] = []
        for other in self.get_all():
            other_id = str(other.get("id"))
            if other_id == source_id: 
                continue
                
            other_vec = self._vector_store.get(other_id)
            if not other_vec:
                continue
                
            score = self._cosine_similarity(source_vec, other_vec)
            results.append(SearchResult(book=other, score=round(score, 5)))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def health(self) -> dict:
        """Стан сервісу для /health ендпоїнту."""
        return {
            "books_loaded": len(self._books),
            "vectors_indexed": len(self._vector_store),
            "index_complete": self._indexed,
            **is_available(),
        }

    # ── Приватні методи ───────────────────────────────────────────────────────

    def _ensure_index(self):
        """Lazy concurrent-safe ініціалізація векторного індексу."""
        if self._indexed:
            return
        with self._index_lock:
            if self._indexed:  # Double-checked locking
                return
            books = self.get_all()
            existing = len(self._vector_store)
            log.info("Building vector index for %d books (%d already cached)...", len(books), existing)
            
            new_count = 0
            for book in books:
                bid = str(book.get("id"))
                if self._vector_store.get(bid):
                    continue  # Вже проіндексовано
                
                text = f"{book['title']}. {book.get('description', '')}"
                vector = get_embedding(text)
                
                self._vector_store.upsert(bid, vector)
                self._vector_store.flush() # Зберігаємо ПІСЛЯ КОЖНОЇ КНИГИ (інкрементально)
                new_count += 1
                log.info("Indexed book [%s/%d]: %s", new_count, len(books), book['title'])
            
            self._indexed = True

    @staticmethod
    def _load_books() -> list[Book]:
        try:
            with open(BOOKS_FILE, "r", encoding="utf-8") as f:
                books = json.load(f)
            log.info("Loaded %d books from %s", len(books), BOOKS_FILE)
            return books
        except FileNotFoundError:
            log.critical("Books file not found: %s", BOOKS_FILE)
            return []
        except json.JSONDecodeError as exc:
            log.critical("Malformed JSON in books file: %s", exc)
            return []

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):  # різні розміри векторів (embedding vs hash fallback)
            min_len = min(len(a), len(b))
            a, b = a[:min_len], b[:min_len]
        dot = sum(x * y for x, y in zip(a, b))
        norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
        return dot / norm if norm else 0.0

    @staticmethod
    def _parse_json_response(raw: str, fallback: dict) -> dict:
        """Витягує JSON з тексту відповіді LLM, стійко до markdown і зайвих символів."""
        if not raw:
            return fallback
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 < end:
                return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
        log.warning("Could not parse JSON from LLM response, using fallback. Raw: %s", raw[:200])
        return fallback


# ─── Singleton Instance ───────────────────────────────────────────────────────

# Єдиний екземпляр сервісу на весь час роботи сервера
book_service = BookService()
