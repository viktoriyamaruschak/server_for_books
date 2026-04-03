@echo off
chcp 65001 >nul
title AI Book Search API

echo ========================================
echo    📚 AI Book Search 
echo ========================================
echo.

if not exist "venv" (
    echo 📦 Створюємо віртуальне середовище...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo 📥 Встановлюємо залежності...
pip install fastapi uvicorn requests pydantic -q

echo.
echo ⚠️  ВАЖЛИВО: Переконайся, що в тебе запущений LM Studio (Local Server на порту 1234)
echo.
echo 🚀 Запуск сервера...
echo    Документація та тестування: http://localhost:8000/docs
echo    З емулятора Android:       http://10.0.2.2:8000
echo.

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
