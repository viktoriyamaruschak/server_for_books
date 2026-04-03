import requests
import sys

def test_endpoint(name, url, method="GET", json_data=None):
    print(f"Testing {name} ({url})...", end=" ", flush=True)
    try:
        if method == "GET":
            r = requests.get(url, timeout=5)
        else:
            r = requests.post(url, json=json_data, timeout=15)
        
        if r.status_code == 200:
            print("✅ OK")
            return True
        else:
            print(f"❌ FAILED (Status: {r.status_code})")
            print(f"   Response: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    base = "http://localhost:8000"
    print("--- 🩺 API DIAGNOSTICS ---")
    
    if not test_endpoint("Root", f"{base}/"):
        print("\n🆘 Сервер не запущений або порт 8000 зайнятий іншим додатком!")
        print("Спробуй запустити 'start.bat' і дочекайся повідомлення 'Uvicorn running on...'")
        return

    test_endpoint("Get Books", f"{base}/api/books")
    test_endpoint("Search", f"{base}/api/search", "POST", {"query": "adventure story"})
    test_endpoint("Profile", f"{base}/api/book/1/profile")
    test_endpoint("Similar", f"{base}/api/similar", "POST", {"book_title": "Dracula"})

    print("\n--- 🧠 LM STUDIO CHECK ---")
    test_endpoint("LM Studio", "http://localhost:1234/v1/models")
    
    print("\nПеревір результат. Якщо LM Studio ❌, то пошук буде працювати в 'спрощеному' режимі.")

if __name__ == "__main__":
    main()
