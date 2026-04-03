import requests
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "books_full_1100_v2.json"
SOURCE_FILE = BASE_DIR / "sample_books.json"
TARGET_TOTAL = 1100

def fetch():
    print(f"🚀 Починаємо збір до {TARGET_TOTAL} книг...")
    
    # Завантажуємо початкові 100 книг
    try:
        with open(SOURCE_FILE, "r", encoding="utf-8") as f:
            all_books = json.load(f)[:100]
        print(f"✅ Завантажено початкові {len(all_books)} книг.")
    except Exception as e:
        print(f"❌ Помилка читання sample_books.json: {e}")
        all_books = []

    existing_titles = {b["title"].lower() for b in all_books}
    next_url = "https://gutendex.com/books/?languages=en&topic=fiction"

    while len(all_books) < TARGET_TOTAL and next_url:
        try:
            print(f"📦 Запит до API: {next_url}")
            r = requests.get(next_url, timeout=30)
            if r.status_code != 200:
                print(f"⚠️ Помилка API: {r.status_code}. Чекаємо...")
                time.sleep(5)
                continue
                
            data = r.json()
            next_url = data.get("next")
            
            for item in data.get("results", []):
                title = item.get("title", "Unknown")
                if title.lower() in existing_titles: continue
                
                summs = item.get("summaries", [])
                if not summs: continue
                
                b_id = str(item.get("id"))
                author = item["authors"][0]["name"] if item.get("authors") else "Unknown"
                
                all_books.append({
                    "id": b_id,
                    "title": title,
                    "author": author,
                    "genre": item.get("subjects", ["Fiction"])[0],
                    "year": 1900,
                    "description": summs[0],
                    "cover_url": f"https://www.gutenberg.org/cache/epub/{b_id}/pg{b_id}.cover.medium.jpg"
                })
                existing_titles.add(title.lower())
                
                if len(all_books) >= TARGET_TOTAL: break
            
            print(f"📊 Зібрано: {len(all_books)} книг.")
            # Зберігаємо проміжний результат у НОВИЙ файл
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_books, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"❌ Помилка: {e}")
            time.sleep(2)

    print(f"✨ ГОТОВО! Файл створено: {OUTPUT_FILE}")
    print(f"Фінальна кількість: {len(all_books)}")

if __name__ == "__main__":
    fetch()
