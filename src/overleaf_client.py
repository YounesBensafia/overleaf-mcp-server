import requests
import os
import git
from config.config import config

class OverleafClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {config.token}"})
        self.base_url = config.base_url
        self.repo_dir = "/tmp/overleaf_repos"
        os.makedirs(self.repo_dir, exist_ok=True)

    def _get_repo_path(self, project_id: str):
        return os.path.join(self.repo_dir, project_id)

    def _get_git_url(self, project_id: str):
        # Overleaf Git URL format: https://git.overleaf.com/PROJECT_ID
        # Using token in URL for authentication
        # Note: In real scenarios, git auth uses the token as username and empty password
        url = self.base_url.replace("https://", "")
        return f"https://{config.token}:@{url}/git/{project_id}"

    def ensure_repo(self, project_id: str):
        repo_path = self._get_repo_path(project_id)
        if not os.path.exists(os.path.join(repo_path, ".git")):
            print(f"Cloning project {project_id}...")
            git.Repo.clone_from(self._get_git_url(project_id), repo_path)
        else:
            print(f"Pulling latest changes for {project_id}...")
            repo = git.Repo(repo_path)
            repo.remotes.origin.pull()
        return repo_path

    def fetch_project_files(self, project_id: str):
        repo_path = self.ensure_repo(project_id)
        files = []
        for root, _, filenames in os.walk(repo_path):
            if ".git" in root:
                continue
            for f in filenames:
                rel_path = os.path.relpath(os.path.join(root, f), repo_path)
                files.append(rel_path)
        return files

    def read_file(self, project_id: str, file_path: str):
        repo_path = self.ensure_repo(project_id)
        full_path = os.path.join(repo_path, file_path)
        if os.path.exists(full_path):
            with open(full_path, 'r') as f:
                return f.read()
        return f"Error: File {file_path} not found."

    def write_file(self, project_id: str, file_path: str, content: str):
        repo_path = self.ensure_repo(project_id)
        full_path = os.path.join(repo_path, file_path)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w') as f:
            f.write(content)
        
        # Commit and push
        repo = git.Repo(repo_path)
        repo.index.add([file_path])
        repo.index.commit(f"Update {file_path} via MCP server")
        repo.remotes.origin.push()
        return True

    def compile_project(self, project_id: str):
        # Triggering compilation via API might still require a different token or web session bit
        # This remains a placeholder for real API integration as Git doesn't handle compilation
        return "Compilation triggered (mock)"
