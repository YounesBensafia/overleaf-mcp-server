import os
from dotenv import load_dotenv

load_dotenv()

OVERLEAF_TOKEN = os.getenv("OVERLEAF_TOKEN")
OVERLEAF_BASE_URL = os.getenv("OVERLEAF_BASE_URL", "https://www.overleaf.com")
PROJECT_ID = os.getenv("PROJECT_ID")

class Config:
    def __init__(self):
        self.token = OVERLEAF_TOKEN
        self.base_url = OVERLEAF_BASE_URL
        self.project_id = PROJECT_ID

config = Config()
