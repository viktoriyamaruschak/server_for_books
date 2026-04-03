@echo off
echo Cleaning up old junk scripts...
del download_books.py fetch_books_smart.py fetch_no_deps.py fetch_openlibrary.py fetch_real_books.py parse_descriptions.py write_100_real_books.py run_fetch.bat run_ol.bat run_smart.bat py_output.txt >nul 2>&1

echo Starting the final fetch process...
"C:/Users/yuram/AppData/Local/Programs/Python/Python313/python.exe" fetch_books.py

echo.
echo Process complete! You can delete this run_final.bat file as well.
pause
