import os
from .config import settings

DEFAULT_PROMPT = "Eres un asistente profesional de atención al cliente 24/7."

def load_system_prompt():
    os.makedirs(os.path.dirname(settings.PROMPT_FILE), exist_ok=True)
    if not os.path.exists(settings.PROMPT_FILE):
        with open(settings.PROMPT_FILE, "w") as f:
            f.write(DEFAULT_PROMPT)
        return DEFAULT_PROMPT
    with open(settings.PROMPT_FILE) as f:
        return f.read()

def save_system_prompt(prompt):
    with open(settings.PROMPT_FILE, "w") as f:
        f.write(prompt)
