# 📚 Book Search Server

Серверна частина курсової роботи — пошук книг за сюжетом через LM Studio.

## 🚀 Запуск (3 кроки)

### Крок 1 — Запусти LM Studio
1. Відкрий **LM Studio**
2. Завантаж будь-яку модель (рекомендую `Gemma 3 4B` або `Mistral 7B`)
3. Перейди у вкладку **Local Server** → натисни **Start Server**
4. Переконайся що сервер на `http://localhost:1234`

### Крок 2 — Вкажи назву моделі
Відкрий файл `.env` і встав назву своєї моделі:
```
LM_STUDIO_MODEL=gemma-3-4b-it
```
> Назву моделі знайдеш у LM Studio → My Models

### Крок 3 — Запусти сервер
Двічі клікни `start.bat` — він сам встановить все потрібне і запустить сервер.

## 📡 API Ендпоїнти

| Метод | URL | Опис |
|-------|-----|------|
| GET | `/api/books` | Список всіх книг |
| POST | `/api/search` | Пошук природною мовою |
| GET | `/api/book/{id}/profile` | Сюжетний профіль |
| POST | `/api/similar` | Схожі за сюжетом |

### Інтерактивна документація
Після запуску відкрий: **http://localhost:8000/docs**

## 📱 Для Android емулятора
Замість `localhost` використовуй `10.0.2.2`:
```
http://10.0.2.2:8000/api/search
```

## 🧪 Тест через curl
```bash
# Пошук
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"книга про таємне товариство в школі\"}"

# Схожі книги
curl -X POST http://localhost:8000/api/similar \
  -H "Content-Type: application/json" \
  -d "{\"book_title\": \"Гаррі Поттер\"}"
```
