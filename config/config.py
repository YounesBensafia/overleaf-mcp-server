import os

from dotenv import load_dotenv

try:
    load_dotenv()
except Exception as e:
    raise RuntimeError(f"Failed to load .env file: {e}") from e

OVERLEAF_TOKEN = os.getenv("OVERLEAF_TOKEN")
PROJECT_ID = os.getenv("PROJECT_ID")
OVERLEAF_REPO_DIR = os.getenv("OVERLEAF_REPO_DIR", "/tmp/overleaf_repos")
OVERLEAF_BASE_URL = os.getenv("OVERLEAF_BASE_URL", "git.overleaf.com")

class Config:
    def __init__(self):
        try:
            self.token = OVERLEAF_TOKEN
            self.project_id = PROJECT_ID
            self.repo_dir = os.path.expanduser(OVERLEAF_REPO_DIR)
            self.base_url = OVERLEAF_BASE_URL
        except Exception as e:
            raise RuntimeError(f"Invalid configuration: {e}") from e

config = Config()
