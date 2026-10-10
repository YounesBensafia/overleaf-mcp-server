import base64
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from itertools import islice

import git

from config.config import config

GIT_NET_TIMEOUT = 60


class OverleafClient:
    def __init__(
        self,
        repo_dir: str | os.PathLike[str] | None = None,
        token: str | None = None,
        default_project_id: str | None = None,
        remote_base: str = "https://git.overleaf.com",
        sync_ttl: float = 5.0,
    ):
        if shutil.which("git") is None:
            raise RuntimeError("Git executable not found; install Git before starting the server.")
        self.repo_dir = os.path.abspath(os.fspath(repo_dir or config.OVERLEAF_REPO_DIR))
        self._token = token if token is not None else config.OVERLEAF_TOKEN.get_secret_value()
        self._default_project_id = (
            default_project_id if default_project_id is not None else config.PROJECT_ID
        )
        self._remote_base = remote_base.rstrip("/")
        self._sync_ttl = sync_ttl
        if not self._token and self._remote_base.startswith("http"):
            raise ValueError("OVERLEAF_TOKEN is required")
        repo_dir_created = not os.path.exists(self.repo_dir)
        os.makedirs(self.repo_dir, mode=0o700, exist_ok=True)
        if repo_dir_created:
            os.chmod(self.repo_dir, 0o700)

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

    @staticmethod
    def _branch(repo: git.Repo) -> str:
        try:
            return repo.active_branch.name
        except TypeError:
            try:
                ref = str(repo.git.symbolic_ref("--short", "refs/remotes/origin/HEAD"))
                return ref.removeprefix("origin/")
            except git.GitCommandError:
                return "master"

    def _git_env(self) -> dict[str, str]:
        entries = [("core.hooksPath", os.devnull)]
        if self._token:
            cred = base64.b64encode(f"git:{self._token}".encode()).decode()
            entries.append(("http.extraHeader", f"Authorization: Basic {cred}"))
        env = {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_HTTP_LOW_SPEED_LIMIT": "1000",
            "GIT_HTTP_LOW_SPEED_TIME": "30",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
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

    def scrub(self, text: str) -> str:
        if self._token:
            text = text.replace(self._token, "***")
            cred = base64.b64encode(f"git:{self._token}".encode()).decode()
            text = text.replace(cred, "***")
        return text

    @contextmanager
    def _scrubbed(self) -> Iterator[None]:
        try:
            yield
        except git.GitCommandError as e:
            raise RuntimeError(self.scrub(str(e))) from None

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
                    git.Repo.clone_from(
                        self._remote_url(project_id),
                        path,
                        env=env,
                        kill_after_timeout=GIT_NET_TIMEOUT,
                    )
                    repo = git.Repo(path)
                    try:
                        with repo.git.custom_environment(**env):
                            repo.git.remote("set-head", "origin", "--auto")
                    except git.GitCommandError:
                        pass
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
                repo.git.fetch("origin", kill_after_timeout=GIT_NET_TIMEOUT)
                branch = self._branch(repo)
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

    def read_file(
        self,
        file_path: str,
        project_id: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> str:
        if offset < 0:
            raise ValueError("offset must be non-negative.")
        if limit is not None and not 0 < limit <= config.MAX_READ_LINES:
            raise ValueError(f"limit must be between 1 and {config.MAX_READ_LINES}.")
        pid = self._resolve_project_id(project_id)
        with self._get_project_lock(pid):
            root = self._sync_unlocked(pid, force=False)
            full, rel = self._safe_path(root, file_path)
            if not os.path.isfile(full):
                raise FileNotFoundError(f"File '{file_path}' not found.")
            try:
                with open(full, encoding="utf-8", newline="") as f:
                    stop = None if limit is None else offset + limit
                    chunks: list[str] = []
                    total_bytes = 0
                    for line in islice(f, offset, stop):
                        total_bytes += len(line.encode("utf-8"))
                        if total_bytes > config.MAX_READ_BYTES:
                            raise ValueError(
                                f"Requested content exceeds {config.MAX_READ_BYTES} bytes."
                            )
                        chunks.append(line)
                    return "".join(chunks)
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
                branch = self._branch(repo)
                try:
                    repo.git.push(
                        "origin",
                        f"HEAD:refs/heads/{branch}",
                        kill_after_timeout=GIT_NET_TIMEOUT,
                    )
                except git.GitCommandError as e:
                    msg = self.scrub(str(e))
                    try:
                        repo.git.fetch("origin", kill_after_timeout=GIT_NET_TIMEOUT)
                        landed = (
                            repo.git.rev_list("--count", f"origin/{branch}..HEAD").strip() == "0"
                        )
                    except git.GitCommandError:
                        landed = None

                    if landed:
                        return f"Pushed '{git_rel}' (confirmed after error). {msg}"
                    if landed is None:
                        raise RuntimeError(
                            "Push result unknown; re-read the file before retrying. " + msg
                        ) from None
                    if "rejected" in msg.lower() or "non-fast-forward" in msg.lower():
                        repo.git.reset("--hard", f"origin/{branch}")
                        self._last_sync[pid] = time.monotonic()
                        raise RuntimeError(
                            "Push rejected; your change was discarded. Re-read and retry. " + msg
                        ) from None
                    raise RuntimeError(msg) from None
                sha = repo.head.commit.hexsha[:8]
            return f"Updated '{git_rel}' and pushed to Overleaf ({sha})"
