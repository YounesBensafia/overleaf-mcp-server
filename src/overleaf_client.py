import os
import git
from config.config import config


class OverleafClient:
    """Overleaf project client using Git sync."""

    def __init__(self):
        self.repo_dir = config.repo_dir
        os.makedirs(self.repo_dir, exist_ok=True)

    def _resolve_project_id(self, project_id: str | None) -> str:
        resolved = project_id or config.project_id
        if not resolved:
            raise ValueError("project_id is required (or set PROJECT_ID in .env)")
        return resolved

    def _get_project_path(self, project_id: str) -> str:
        return os.path.join(self.repo_dir, project_id)

    def _get_git_url(self, project_id: str) -> str:
        if not config.token:
            raise ValueError("OVERLEAF_TOKEN is required")
        return f"https://git:{config.token}@git.overleaf.com/{project_id}"

    def ensure_repo(self, project_id: str | None = None) -> str:
        """Clone or pull an Overleaf repo and return the local path."""
        resolved_project_id = self._resolve_project_id(project_id)
        repo_path = self._get_project_path(resolved_project_id)

        if not os.path.exists(os.path.join(repo_path, ".git")):
            repo = git.Repo.clone_from(self._get_git_url(resolved_project_id), repo_path)
            repo.git.config("--add", "remote.origin.fetch", "+refs/heads/*:refs/heads/*")
        else:
            repo = git.Repo(repo_path)
            try:
                repo.git.config("remote.origin.fetch")
            except git.GitCommandError:
                repo.git.config("--add", "remote.origin.fetch", "+refs/heads/*:refs/heads/*")
            repo.remotes.origin.pull()

        return repo_path

    def list_files(self, project_id: str | None = None) -> list[str]:
        project_path = self.ensure_repo(project_id)
        files = []
        for root, _, filenames in os.walk(project_path):
            if any(part.startswith(".") for part in root.split(os.sep)):
                continue
            for filename in filenames:
                rel_path = os.path.relpath(os.path.join(root, filename), project_path)
                files.append(rel_path)
        return files

    def read_file(self, file_path: str, project_id: str | None = None) -> str:
        project_path = self.ensure_repo(project_id)
        full_path = os.path.join(project_path, file_path)
        if not os.path.exists(full_path):
            return f"Error: File '{file_path}' not found."
        with open(full_path, "r", encoding="utf-8") as file:
            return file.read()

    def write_file(self, file_path: str, content: str, project_id: str | None = None) -> str:
        project_path = self.ensure_repo(project_id)
        full_path = os.path.join(project_path, file_path)

        dir_path = os.path.dirname(full_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as file:
            file.write(content)

        repo = git.Repo(project_path)
        repo.index.add([file_path])
        repo.index.commit(f"Update {file_path} via Overleaf MCP")
        repo.remotes.origin.push()
        return f"Updated '{file_path}' and pushed to Overleaf"
