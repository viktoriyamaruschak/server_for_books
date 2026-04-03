@echo off
"C:/Users/yuram/AppData/Local/Programs/Python/Python313/python.exe" -c "import traceback; try: import main; print('MAIN HAS NO SYNTAX ERRORS')\nexcept Exception: traceback.print_exc()" > capture_error.log 2>&1
echo Done >> capture_error.log
