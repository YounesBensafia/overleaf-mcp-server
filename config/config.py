import os
from dotenv import load_dotenv

try:
    load_dotenv()
except Exception as e:
    raise RuntimeError(f"Failed to load .env file: {e}") from e

OVERLEAF_TOKEN = os.getenv("OVERLEAF_TOKEN")
OVERLEAF_EMAIL = os.getenv("OVERLEAF_EMAIL")
PROJECT_ID = os.getenv("PROJECT_ID")
OVERLEAF_REPO_DIR = os.getenv("OVERLEAF_REPO_DIR", "/tmp/overleaf_repos")

class Config:
    def __init__(self):
        try:
            self.token = OVERLEAF_TOKEN
            self.email = OVERLEAF_EMAIL
            self.project_id = PROJECT_ID
            self.repo_dir = os.path.expanduser(OVERLEAF_REPO_DIR)
        except Exception as e:
            raise RuntimeError(f"Invalid configuration: {e}") from e

config = Config()
