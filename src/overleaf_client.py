import base64
import os
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager

import git

from config.config import config



class OverleafClient:
    def __init__(
        self,
        repo_dir: str | None = None,
        token: str | None = None,
        default_project_id: str | None = None,
        remote_base: str = "https://git.overleaf.com",
        sync_ttl: float = 5.0,
    ):
        self.repo_dir = os.path.abspath(repo_dir or config.OVERLEAF_REPO_DIR)
        self._token = token if token is not None else config.OVERLEAF_TOKEN
        self._default_project_id = (
            default_project_id if default_project_id is not None else config.PROJECT_ID
        )
        self._remote_base = remote_base.rstrip("/")
        self._sync_ttl = sync_ttl
        if not self._token and self._remote_base.startswith("http"):
            raise ValueError("OVERLEAF_TOKEN is required")
        os.makedirs(self.repo_dir, exist_ok=True)

        self._project_locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()
        self._last_sync: dict[str, float] = {}


    def _get_project_lock(self, project_id: str) -> threading.Lock:
        with self._locks_lock:
            return self._project_locks.setdefault(project_id, threading.Lock())

    def _resolve_project_id(self, project_id: str | None) -> str:
        resolved = self._default_project_id if project_id is None else project_id
        if not resolved:
            raise ValueError("project_id is required (or set PROJECT_ID in .env)")
        if not config.PROJECT_ID_RE.fullmatch(resolved):
            raise ValueError("Invalid project_id (expected 24 hex characters).")
        return resolved

    def _project_path(self, project_id: str) -> str:
        return os.path.join(self.repo_dir, project_id)

    def _remote_url(self, project_id: str) -> str:
        return f"{self._remote_base}/{project_id}"

    def _git_env(self) -> dict[str, str]:
        entries = [("core.hooksPath", os.devnull)]
        if self._token:
            cred = base64.b64encode(f"git:{self._token}".encode()).decode()
            entries.append(("http.extraHeader", f"Authorization: Basic {cred}"))
        env = {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": config.IDENTITY[0],
            "GIT_AUTHOR_EMAIL": config.IDENTITY[1],
            "GIT_COMMITTER_NAME": config.IDENTITY[0],
            "GIT_COMMITTER_EMAIL": config.IDENTITY[1],
            "GIT_CONFIG_COUNT": str(len(entries)),
        }
        for i, (key, value) in enumerate(entries):
            env[f"GIT_CONFIG_KEY_{i}"] = key
            env[f"GIT_CONFIG_VALUE_{i}"] = value
        return env

    def _scrub(self, text: str) -> str:

        if self._token:
            text = text.replace(self._token, "***")
            cred = base64.b64encode(f"git:{self._token}".encode()).decode()
            text = text.replace(cred, "***")
        return text

    @contextmanager
    def _scrubbed(self):
        try:
            yield
        except git.GitCommandError as e:
            raise RuntimeError(self._scrub(str(e))) from None

    @staticmethod
    def _safe_path(project_path: str, file_path: str) -> tuple[str, str]:
        if not file_path or "\x00" in file_path:
            raise ValueError("Invalid file path.")
        root = os.path.realpath(project_path)
        full = os.path.realpath(os.path.join(root, file_path))
        try:
            inside = os.path.commonpath([root, full]) == root
        except ValueError:
            inside = False
        if not inside or full == root:
            raise ValueError(f"Path '{file_path}' is outside the project directory.")
        rel = os.path.relpath(full, root)
        if any(part.lower() == ".git" for part in rel.split(os.sep)):
            raise ValueError("Access to the .git directory is not allowed.")
        return full, rel

    @staticmethod
    def _atomic_write(full_path: str, data: bytes) -> None:
        directory = os.path.dirname(full_path)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            if os.path.exists(full_path):
                shutil.copymode(full_path, tmp)
            os.replace(tmp, full_path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def _sync_unlocked(self, project_id: str, force: bool) -> str:
        path = self._project_path(project_id)
        env = self._git_env()

        if not os.path.isdir(os.path.join(path, ".git")):
            try:
                with self._scrubbed():
                    git.Repo.clone_from(self._remote_url(project_id), path, env=env)
            except BaseException:
                shutil.rmtree(path, ignore_errors=True)
                raise
        else:
            age = time.monotonic() - self._last_sync.get(project_id, float("-inf"))
            if not force and age < self._sync_ttl:
                return path
            repo = git.Repo(path)
            with self._scrubbed(), repo.git.custom_environment(**env):
                repo.git.remote("set-url", "origin", self._remote_url(project_id))
                repo.git.config(
                    "--replace-all", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"
                )
                repo.git.fetch("origin")
                branch = repo.active_branch.name
                repo.git.reset("--hard", f"origin/{branch}")
                repo.git.clean("-fd")

        self._last_sync[project_id] = time.monotonic()
        return path

    def ensure_repo(self, project_id: str | None = None) -> str:
        pid = self._resolve_project_id(project_id)
        with self._get_project_lock(pid):
            return self._sync_unlocked(pid, force=True)

    def list_files(self, project_id: str | None = None) -> list[str]:
        pid = self._resolve_project_id(project_id)
        with self._get_project_lock(pid):
            root = self._sync_unlocked(pid, force=False)
            files = []
            for current, dirs, filenames in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in filenames:
                    if not name.startswith("."):
                        rel = os.path.relpath(os.path.join(current, name), root)
                        files.append(rel.replace(os.sep, "/"))
            return sorted(files)

    def read_file(self, file_path: str, project_id: str | None = None) -> str:
        pid = self._resolve_project_id(project_id)
        with self._get_project_lock(pid):
            root = self._sync_unlocked(pid, force=False)
            full, rel = self._safe_path(root, file_path)
            if not os.path.isfile(full):
                raise FileNotFoundError(f"File '{file_path}' not found.")
            if os.path.getsize(full) > config.MAX_READ_BYTES:
                raise ValueError(f"'{rel}' is larger than {config.MAX_READ_BYTES} bytes.")
            try:
                with open(full, "r", encoding="utf-8", newline="") as f:
                    return f.read()
            except UnicodeDecodeError:
                raise ValueError(f"'{rel}' is not a UTF-8 text file.") from None


    def write_file(self, file_path: str, content: str, project_id: str | None = None) -> str:
        pid = self._resolve_project_id(project_id)
        data = content.encode("utf-8")
        if len(data) > config.MAX_WRITE_BYTES:
            raise ValueError(f"Content is larger than {config.MAX_WRITE_BYTES} bytes.")

        with self._get_project_lock(pid):
            root = self._sync_unlocked(pid, force=True)
            full, rel = self._safe_path(root, file_path)
            git_rel = rel.replace(os.sep, "/")
            self._atomic_write(full, data)

            repo = git.Repo(root)
            with self._scrubbed(), repo.git.custom_environment(**self._git_env()):
                if not repo.git.status("--porcelain", "--", git_rel).strip():
                    return f"No changes: '{git_rel}' already has this content."

                repo.git.add("--", git_rel)
                repo.git.commit("-m", f"Update {git_rel} via Overleaf MCP")
                branch = repo.active_branch.name
                try:
                    repo.git.push("origin", f"HEAD:refs/heads/{branch}")
                except git.GitCommandError as e:
                    repo.git.fetch("origin")
                    repo.git.reset("--hard", f"origin/{branch}")
                    self._last_sync[pid] = time.monotonic()
                    raise RuntimeError(
                        "Push rejected; your change was discarded. "
                        "Re-read the file and retry. " + self._scrub(str(e))
                    ) from None
                sha = repo.head.commit.hexsha[:8]
            return f"Updated '{git_rel}' and pushed to Overleaf ({sha})"