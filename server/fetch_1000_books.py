import requests
import json
import time
import sys

# --- НАЛАШТУВАННЯ ---
TARGET_COUNT = 1000
GUTENDEX_URL = "https://gutendex.com/books/"
# Робимо шлях абсолютним відносно скрипта
BASE_DIR = Path(__file__).parent
EXISTING_FILE = BASE_DIR / "sample_books.json"

def fetch_books():
    """Завантажує 1000 книг з описами сюжетов (інкрементально)"""
    print(f"🚀 Починаю збір {TARGET_COUNT} книг...", flush=True)
    
    # 1. Завантажуємо існуючі книги
    all_books = []
    if EXISTING_FILE.exists():
        try:
            with open(EXISTING_FILE, "r", encoding="utf-8") as f:
                all_books = json.load(f)
            print(f"✅ Вже маємо в базі: {len(all_books)} книг.", flush=True)
        except Exception as e:
            print(f"⚠️ Помилка читання файлу: {e}. Починаємо з нуля.", flush=True)
    else:
        print(f"💡 Файл {EXISTING_FILE.name} не знайдено. Створюємо нову базу.", flush=True)

    existing_titles = {b["title"].lower() for b in all_books}
    original_count = len(all_books)
    
    next_url = GUTENDEX_URL + "?languages=en&topic=fiction"

    while len(all_books) < (TARGET_COUNT + original_count) and next_url:
        try:
            print(f"📦 Завантажую сторінку: {next_url}", flush=True)
            # Збільшили timeout до 30 секунд
            resp = requests.get(next_url, timeout=30)
            
            if resp.status_code == 429:
                print("⚠️ Забагато запитів (Rate Limit). Чекаю 10 секунд...", flush=True)
                time.sleep(10)
                continue
                
            if resp.status_code != 200:
                print(f"⚠️ Помилка API: {resp.status_code}. Чекаю 5 сек...", flush=True)
                time.sleep(5)
                continue
                
            data = resp.json()
            next_url = data.get("next")
            results = data.get("results", [])
            
            new_this_page = 0
            for item in results:
                title = item.get("title", "Unknown")
                if title.lower() in existing_titles:
                    continue
                
                summaries = item.get("summaries", [])
                if not summaries:
                    continue
                
                description = summaries[0]
                book_id = str(item.get("id"))
                
                author = "Unknown"
                if item.get("authors"):
                    author = item["authors"][0].get("name", "Unknown")
                
                year = 1900
                if item.get("authors") and item["authors"][0].get("birth_year"):
                    year = item["authors"][0].get("birth_year") + 30

                new_book = {
                    "id": book_id,
                    "title": title,
                    "author": author,
                    "genre": item.get("subjects", ["Fiction"])[0],
                    "year": year,
                    "description": description,
                    "cover_url": f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.cover.medium.jpg"
                }

                all_books.append(new_book)
                existing_titles.add(title.lower())
                new_this_page += 1
                
                # Зберігаємо КОЖНІ 20 книг
                if len(all_books) % 20 == 0:
                    with open(EXISTING_FILE, "w", encoding="utf-8") as f:
                        json.dump(all_books, f, ensure_ascii=False, indent=2)
                    print(f"💾 Файл оновлено! Разом: {len(all_books)} книг.", flush=True)
                
                if len(all_books) >= (TARGET_COUNT + original_count):
                    break
            
            print(f"📊 Додано з цієї сторінки: {new_this_page} книг.", flush=True)
            # Невелика пауза щоб не злити API
            time.sleep(1)

        except (requests.exceptions.RequestException, Exception) as e:
            print(f"❌ Помилка з'єднання: {e}. Спробую ще раз через 5 сек...", flush=True)
            time.sleep(5)

    # Фінальне збереження
    with open(EXISTING_FILE, "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False, indent=2)
    
    print(f"\n✨ ЗАВЕРШЕНО! Усього в базі: {len(all_books)} книг.", flush=True)

if __name__ == "__main__":
    fetch_books()
