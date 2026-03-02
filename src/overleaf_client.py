import requests
from config.config import config

class OverleafClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {config.token}"})
        self.base_url = config.base_url

    def fetch_project_files(self, project_id: str):
        # Implementation to fetch list of files from Overleaf API/Git
        pass

    def read_file(self, project_id: str, file_path: str):
        # Implementation to read content of a specific file
        pass

    def compile_project(self, project_id: str):
        # Implementation to trigger compilation
        pass
