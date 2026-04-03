import requests
import json
import time
import os

TARGET_BOOKS = 1000

def main():
    books = []
    existing_titles = set()
    file_path = os.path.join(os.path.dirname(__file__), "sample_books.json")
    
    print("Починаємо парсинг реальних книг з OpenLibrary API...")
    
    # Використовуємо заголовки, щоб сервер не блокував запити від Python
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # Робимо запити по сторінках (по 100 книг на сторінку)
    page = 1
    while len(books) < TARGET_BOOKS:
        url = f"https://openlibrary.org/search.json?subject=fiction&limit=100&page={page}"
        print(f"Завантаження сторінки {page}... (вже зібрано: {len(books)})")
        
        try:
            r = requests.get(url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                print(f"Сервер повернув статус {r.status_code}. Затримка 5 секунд...")
                time.sleep(5)
                continue
                
            data = r.json()
            docs = data.get("docs", [])
            
            if not docs:
                print("Більше немає результатів. Змінюємо жанр...")
                break
                
            for doc in docs:
                if len(books) >= TARGET_BOOKS:
                    break
                    
                title = doc.get("title", "")
                if not title or title.lower() in existing_titles:
                    continue
                    
                authors = doc.get("author_name", ["Unknown"])
                author = authors[0] if authors else "Unknown"
                
                year = doc.get("first_publish_year", 1900)
                
                # Отримання обкладинки, якщо вона є в базі
                cover_id = doc.get("cover_i")
                if cover_id:
                    cover = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                else:
                    cover = "https://www.gutenberg.org/cache/epub/175/pg175.cover.medium.jpg"
                    
                desc = f'"{title}" is a notable work by {author}, first published in {year}. It is widely recognized in the fiction genre and remains a significant part of literary collections.'
                
                books.append({
                    "id": str(len(books) + 1),
                    "title": title,
                    "author": author,
                    "genre": "Fiction",
                    "year": year,
                    "description": desc,
                    "cover_url": cover
                })
                existing_titles.add(title.lower())
            
            # Збереження прогресу після кожної сторінки
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(books, f, ensure_ascii=False, indent=2)
                
            page += 1
            time.sleep(1.5) 
            
        except requests.exceptions.RequestException as e:
            print(f"Помилка мережі: {e}. Спроба повтору через 5 секунд...")
            time.sleep(5)

    print(f"\nГотово. У файл {file_path} завантажено {len(books)} реальних книг.")

if __name__ == "__main__":
    main()