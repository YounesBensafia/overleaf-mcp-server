import os
from dotenv import load_dotenv

load_dotenv()

OVERLEAF_TOKEN = os.getenv("OVERLEAF_TOKEN")
OVERLEAF_EMAIL = os.getenv("OVERLEAF_EMAIL")
OVERLEAF_BASE_URL = os.getenv("OVERLEAF_BASE_URL", "https://www.overleaf.com")
PROJECT_ID = os.getenv("PROJECT_ID")
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("true", "1", "yes")

class Config:
    def __init__(self):
        self.token = OVERLEAF_TOKEN
        self.email = OVERLEAF_EMAIL
        self.base_url = OVERLEAF_BASE_URL
        self.project_id = PROJECT_ID
        self.mock_mode = MOCK_MODE

config = Config()
