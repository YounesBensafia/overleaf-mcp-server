import os
from dotenv import load_dotenv

load_dotenv()

# Mode: "local" (default) or "overleaf" (requires premium)
MODE = os.getenv("MODE", "local")

# Local mode settings
PROJECT_PATH = os.getenv("PROJECT_PATH", os.getcwd())

# Overleaf mode settings (optional, requires premium)
OVERLEAF_TOKEN = os.getenv("OVERLEAF_TOKEN")
OVERLEAF_EMAIL = os.getenv("OVERLEAF_EMAIL")
PROJECT_ID = os.getenv("PROJECT_ID")

class Config:
    def __init__(self):
        self.mode = MODE
        self.project_path = PROJECT_PATH
        self.token = OVERLEAF_TOKEN
        self.email = OVERLEAF_EMAIL
        self.project_id = PROJECT_ID

config = Config()
