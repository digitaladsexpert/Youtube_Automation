#!/usr/bin/env bash
set -e
echo "Creating Virtual Environment..."
python3 -m venv venv
source venv/bin/activate
echo "Installing Requirements..."
pip install --upgrade pip
pip install -r requirements.txt
echo "Setup Complete! Run: python run.py"
