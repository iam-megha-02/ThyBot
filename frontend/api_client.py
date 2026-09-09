import os

import requests

BASE_URL = os.environ.get("THYBOT_BACKEND_URL", "http://127.0.0.1:8000")
TIMEOUT_SECONDS = 60


def check_backend_health() -> dict:
    response = requests.get(f"{BASE_URL}/health", timeout=5)
    response.raise_for_status()
    return response.json()


def ask_question(question: str) -> dict:
    response = requests.post(f"{BASE_URL}/chat", json={"question": question}, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()
