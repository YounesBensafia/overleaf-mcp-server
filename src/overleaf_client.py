import os
import threading

import git

from config.config import config


class OverleafClient:
    def __init__(self):
        self.repo_dir = config.repo_dir
        os.makedirs(self.repo_dir, exist_ok=True)
        self._project_locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    def _get_project_lock(self, project_id: str) -> threading.Lock:
        with self._locks_lock:
            if project_id not in self._project_locks:
                self._project_locks[project_id] = threading.Lock()
            return self._project_locks[project_id]

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
        base = config.base_url.rstrip("/")
        if "://" in base:
            base = base.split("://", 1)[1]
        return f"https://git:{config.token}@{base}/{project_id}"

    def ensure_repo(self, project_id: str | None = None) -> str:
        resolved_project_id = self._resolve_project_id(project_id)
        lock = self._get_project_lock(resolved_project_id)
        with lock:
            repo_path = self._get_project_path(resolved_project_id)

            if not os.path.exists(os.path.join(repo_path, ".git")):
                repo = git.Repo.clone_from(self._get_git_url(resolved_project_id), repo_path)
                repo.git.config("remote.origin.fetch", "+refs/heads/*:refs/heads/*")
            else:
                repo = git.Repo(repo_path)
                try:
                    existing = repo.git.config("--get-all", "remote.origin.fetch")
                except git.GitCommandError:
                    existing = ""
                existing = existing.strip() if existing else ""
                if "+refs/heads/*:refs/heads/*" not in existing:
                    repo.git.config("--add", "remote.origin.fetch", "+refs/heads/*:refs/heads/*")
                repo.remotes.origin.pull()

            return repo_path

    def list_files(self, project_id: str | None = None) -> list[str]:
        project_path = self.ensure_repo(project_id)
        files = []
        for root, _, filenames in os.walk(project_path):
            if root == project_path:
                for filename in filenames:
                    if filename.startswith("."):
                        continue
                    rel_path = os.path.relpath(os.path.join(root, filename), project_path)
                    files.append(rel_path)
                continue
            rel_root = os.path.relpath(root, project_path)
            if any(part.startswith(".") for part in rel_root.split(os.sep)):
                continue
            for filename in filenames:
                if filename.startswith("."):
                    continue
                rel_path = os.path.relpath(os.path.join(root, filename), project_path)
                files.append(rel_path)
        return files

    def read_file(self, file_path: str, project_id: str | None = None) -> str:
        project_path = self.ensure_repo(project_id)
        real_project = os.path.realpath(project_path)
        full_path = os.path.realpath(os.path.join(project_path, file_path))
        if not full_path.startswith(real_project + os.sep) and full_path != real_project:
            raise ValueError(f"Path '{file_path}' is outside the project directory.")
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File '{file_path}' not found.")
        with open(full_path, "r", encoding="utf-8") as file:
            return file.read()

    def write_file(self, file_path: str, content: str, project_id: str | None = None) -> str:
        project_path = self.ensure_repo(project_id)
        real_project = os.path.realpath(project_path)
        full_path = os.path.realpath(os.path.join(project_path, file_path))
        if not full_path.startswith(real_project + os.sep) and full_path != real_project:
            raise ValueError(f"Path '{file_path}' is outside the project directory.")

        dir_path = os.path.dirname(full_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as file:
            file.write(content)

        lock = self._get_project_lock(project_id)
        with lock:
            repo = git.Repo(project_path)
            repo.index.add([file_path])
            repo.index.commit(f"Update {file_path} via Overleaf MCP")
            repo.remotes.origin.push()
        return f"Updated '{file_path}' and pushed to Overleaf"
