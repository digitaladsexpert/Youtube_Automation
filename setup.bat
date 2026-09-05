@echo off
echo Creating Virtual Environment...
python -m venv venv
call venv\Scripts\activate.bat
echo Installing Requirements...
pip install --upgrade pip
pip install -r requirements.txt
echo Setup Complete! Run: python run.py
pause