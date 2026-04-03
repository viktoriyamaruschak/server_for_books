import requests
import json
import time

BASE_URL = "http://localhost:8000"

def log_test(name, result):
    print(f"\n--- 🧪 TEST: {name} ---")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1000] + ("..." if len(str(result)) > 1000 else ""))

def main():
    print("🚀 Starting Professional API Test...")
    
    # ПЕРЕВІРКА 1: Інтелектуальний пошук природною мовою
    try:
        search_res = requests.post(
            f"{BASE_URL}/api/search", 
            json={"query": "історія про закриту школу та таємне товариство", "limit": 3},
            timeout=30
        ).json()
        log_test("Natural Language Search", search_res)
    except Exception as e:
        print(f"❌ Search failed: {e}")

    # ПЕРЕВІРКА 2: Генерація сюжетного профілю
    # Спершу візьмемо ID першої книги з результатів пошуку
    try:
        book_id = search_res["results"][0]["book"]["id"]
        profile_res = requests.get(f"{BASE_URL}/api/book/{book_id}/profile", timeout=30).json()
        log_test("AI Plot Profiling", profile_res)
    except Exception as e:
        print(f"❌ Profiling failed: {e}")

    # ПЕРЕВІРКА 3: Контекстне порівняння за назвою
    try:
        # Спробуємо знайти аналоги для "Frankenstein"
        similar_res = requests.post(
            f"{BASE_URL}/api/similar", 
            json={"book_title": "Frankenstein; or, the modern prometheus", "limit": 3},
            timeout=30
        ).json()
        log_test("Contextual Comparison (by Title)", similar_res)
    except Exception as e:
        print(f"❌ Similarity failed: {e}")

if __name__ == "__main__":
    main()
