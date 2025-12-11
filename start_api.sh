#!/bin/bash
# Startup script for HTML Extractor API on EC2

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install dependencies if needed
if [ ! -f ".api_installed" ]; then
    echo "Installing API dependencies..."
    pip install -r requirements_api.txt
    playwright install chromium
    touch .api_installed
fi

# Start the API server
echo "Starting HTML Extractor API on port 8000..."
python api.py

