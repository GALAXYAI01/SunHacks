"""
main.py — Entry point for the PredictiveEng server.

Loads environment variables from .env and re-exports the FastAPI ``app``
from main_FINAL.py so that ``uvicorn main:app`` works.

Usage:
    python main.py            # runs on http://0.0.0.0:8000
    uvicorn main:app --reload # alternative
"""

from dotenv import load_dotenv
load_dotenv()                # must come before any module reads os.getenv

from main_FINAL import app   # noqa: E402, F401

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
