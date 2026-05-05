@echo off
echo =======================================
echo        Starting VideoAgent App
echo =======================================

:: Activate the virtual environment
echo Activating Virtual Environment...
call .\venv\Scripts\activate

:: Open the app in the default browser (Chrome)
echo Opening Browser...
start http://127.0.0.1:5858

:: Start the Python Flask server
echo Starting Server...
python app.py

pause
