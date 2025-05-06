# Zoltar AI Assistant Backend

This is the backend service for the Zoltar AI Assistant.

## Setup

1.  Create a virtual environment: `python -m venv venv`
2.  Activate it: `source venv/bin/activate` (or `venv\Scripts\activate` on Windows)
3.  Install dependencies: `pip install -r requirements.txt`

## Running the server

`uvicorn main:app --reload`

The API will be available at http://127.0.0.1:8000 