import base64
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress

import git
from filelock import FileLock, Timeout

from .config import config
from .constants import IDENTITY, MAX_READ_BYTES, MAX_READ_LINES, MAX_WRITE_BYTES

GIT_NET_TIMEOUT = 60
GIT_CLONE_TIMEOUT = 600
PROJECT_LOCK_TIMEOUT = 120


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

    def _get_thread_lock(self, project_id: str) -> threading.Lock:
        with self._locks_lock:
            return self._project_locks.setdefault(project_id, threading.Lock())

    def _resolve_project_id(self, project_id: str | None) -> str:
        resolved = self._default_project_id if project_id is None else project_id
        if not resolved:
            raise ValueError("project_id is required")
        if not config.PROJECT_ID_RE.fullmatch(resolved):
            raise ValueError("Invalid project_id (expected 24 hex characters).")
        configured_projects = {
            item.strip() for item in config.OVERLEAF_ALLOWED_PROJECTS.split(",") if item.strip()
        }
        allowed_projects = configured_projects or {self._default_project_id}
        if resolved not in allowed_projects:
            raise ValueError(f"Project '{resolved}' is not in the allowed project list.")
        return resolved

    def _project_path(self, project_id: str) -> str:
        return os.path.join(self.repo_dir, project_id)

    @contextmanager
    def _project_lock(self, project_id: str) -> Iterator[None]:
        with self._get_thread_lock(project_id):
            try:
                with FileLock(
                    f"{self._project_path(project_id)}.lock", timeout=PROJECT_LOCK_TIMEOUT
                ):
                    yield
            except Timeout:
                raise RuntimeError(
                    "Another process is using this project; retry shortly."
                ) from None

    def _remote_url(self, project_id: str) -> str:
        return f"{self._remote_base}/{project_id}"

    @staticmethod
    def _branch(repo: git.Repo) -> str:
        try:
            branch = repo.active_branch.name
        except TypeError:
            try:
                ref = str(repo.git.symbolic_ref("--short", "refs/remotes/origin/HEAD"))
                branch = ref.removeprefix("origin/")
            except git.GitCommandError:
                branch = "master"
        try:
            repo.git.rev_parse("--verify", f"refs/remotes/origin/{branch}")
        except git.GitCommandError:
            raise RuntimeError(f"Remote branch 'origin/{branch}' was not found.") from None
        return branch

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
            "GIT_AUTHOR_NAME": IDENTITY[0],
            "GIT_AUTHOR_EMAIL": IDENTITY[1],
            "GIT_COMMITTER_NAME": IDENTITY[0],
            "GIT_COMMITTER_EMAIL": IDENTITY[1],
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
                        kill_after_timeout=GIT_CLONE_TIMEOUT,
                    )
                    repo = git.Repo(path)
                    with self._scrubbed(), repo.git.custom_environment(**env):
                        repo.git.remote("set-url", "origin", self._remote_url(project_id))
                        repo.git.config(
                            "--replace-all",
                            "remote.origin.fetch",
                            "+refs/heads/*:refs/remotes/origin/*",
                        )
                        with suppress(git.GitCommandError):
                            repo.git.remote("set-head", "origin", "--auto")
            except BaseException:
                self._remove_cache(path)
                raise
        else:
            age = time.monotonic() - self._last_sync.get(project_id, float("-inf"))
            if not force and age < self._sync_ttl:
                return path
            try:
                repo = git.Repo(path)
            except (git.InvalidGitRepositoryError, git.NoSuchPathError):
                self._remove_cache(path)
                return self._sync_unlocked(project_id, force=True)
            try:
                with self._scrubbed(), repo.git.custom_environment(**env):
                    repo.git.fetch("origin", kill_after_timeout=GIT_NET_TIMEOUT)
                    branch = self._branch(repo)
                    repo.git.reset("--hard", f"origin/{branch}")
                    repo.git.clean("-fd")
            except RuntimeError as exc:
                if str(exc).startswith("Remote branch"):
                    raise
                self._remove_cache(path)
                return self._sync_unlocked(project_id, force=True)

        self._last_sync[project_id] = time.monotonic()
        return path

    @staticmethod
    def _remove_cache(path: str) -> None:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)

    def ensure_repo(self, project_id: str | None = None) -> str:
        pid = self._resolve_project_id(project_id)
        with self._project_lock(pid):
            return self._sync_unlocked(pid, force=True)

    def list_files(self, project_id: str | None = None) -> list[str]:
        pid = self._resolve_project_id(project_id)
        with self._project_lock(pid):
            root = self._sync_unlocked(pid, force=False)
            files = []
            for current, dirs, filenames in os.walk(root):
                dirs[:] = [d for d in dirs if d != ".git" and not d.startswith(".tmp-")]
                for name in filenames:
                    if name != ".git" and not name.startswith(".tmp-"):
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
        if limit is not None and not 0 < limit <= MAX_READ_LINES:
            raise ValueError(f"limit must be between 1 and {MAX_READ_LINES}.")
        pid = self._resolve_project_id(project_id)
        with self._project_lock(pid):
            root = self._sync_unlocked(pid, force=False)
            full, rel = self._safe_path(root, file_path)
            if not os.path.isfile(full):
                raise FileNotFoundError(f"File '{file_path}' not found.")
            try:
                with open(full, encoding="utf-8", newline="") as f:
                    chunks: list[str] = []
                    total_bytes = 0
                    for _ in range(offset):
                        skipped = f.readline(MAX_READ_BYTES + 1)
                        if not skipped:
                            return ""
                        if len(skipped.encode("utf-8")) > MAX_READ_BYTES:
                            raise ValueError(
                                f"Content exceeds {MAX_READ_BYTES} bytes; "
                                "use offset/limit to read in chunks."
                            )
                    lines_read = 0
                    while limit is None or lines_read < limit:
                        line = f.readline(MAX_READ_BYTES + 1)
                        if not line:
                            break
                        total_bytes += len(line.encode("utf-8"))
                        if total_bytes > MAX_READ_BYTES:
                            raise ValueError(
                                f"Content exceeds {MAX_READ_BYTES} bytes; "
                                "use offset/limit to read in chunks."
                            )
                        chunks.append(line)
                        lines_read += 1
                    return "".join(chunks)
            except UnicodeDecodeError:
                raise ValueError(f"'{rel}' is not a UTF-8 text file.") from None

    def _write_synced_file(self, pid: str, root: str, full: str, git_rel: str, data: bytes) -> str:
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
                self._last_sync.pop(pid, None)
                try:
                    repo.git.fetch("origin", kill_after_timeout=GIT_NET_TIMEOUT)
                    ahead = int(repo.git.rev_list("--count", f"origin/{branch}..HEAD"))
                    behind = int(repo.git.rev_list("--count", f"HEAD..origin/{branch}"))
                except (git.GitCommandError, ValueError):
                    raise RuntimeError(
                        "Push result unknown; re-read the file before retrying. " + msg
                    ) from None

                if ahead == 0:
                    return f"Pushed '{git_rel}' (confirmed after error)."
                repo.git.reset("--hard", f"origin/{branch}")
                if behind:
                    raise RuntimeError(
                        "Push rejected: the remote changed. Re-read and retry. " + msg
                    ) from None
                raise RuntimeError("Push failed; your change was discarded. " + msg) from None
            sha = repo.head.commit.hexsha[:8]
        return f"Updated '{git_rel}' and pushed to Overleaf ({sha})"

    def write_file(self, file_path: str, content: str, project_id: str | None = None) -> str:
        pid = self._resolve_project_id(project_id)
        data = content.encode("utf-8")
        if len(data) > MAX_WRITE_BYTES:
            raise ValueError(f"Content is larger than {MAX_WRITE_BYTES} bytes.")

        with self._project_lock(pid):
            root = self._sync_unlocked(pid, force=True)
            full, rel = self._safe_path(root, file_path)
            git_rel = rel.replace(os.sep, "/")
            if os.path.isfile(full):
                try:
                    with open(full, "rb") as existing:
                        existing_text = existing.read().decode("utf-8")
                    if "\x00" in existing_text:
                        raise ValueError(f"'{git_rel}' is not a UTF-8 text file.")
                except UnicodeDecodeError:
                    raise ValueError(f"'{git_rel}' is not a UTF-8 text file.") from None
            return self._write_synced_file(pid, root, full, git_rel, data)

    def edit_file(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
        project_id: str | None = None,
    ) -> str:
        """Replace exactly one occurrence of old_text and push the complete file."""
        if not old_text:
            raise ValueError("old_text must not be empty.")
        pid = self._resolve_project_id(project_id)
        with self._project_lock(pid):
            root = self._sync_unlocked(pid, force=True)
            full, rel = self._safe_path(root, file_path)
            if not os.path.isfile(full):
                raise FileNotFoundError(f"File '{file_path}' not found.")
            try:
                with open(full, encoding="utf-8", newline="") as existing:
                    current = existing.read()
            except UnicodeDecodeError:
                raise ValueError(f"'{rel}' is not a UTF-8 text file.") from None
            matches = current.count(old_text)
            if matches == 0:
                raise ValueError(
                    "old_text was not found in the file; check whitespace and indentation."
                )
            if matches > 1:
                raise ValueError(f"old_text matched {matches} times; it must match exactly once.")
            data = current.replace(old_text, new_text, 1).encode("utf-8")
            if len(data) > MAX_WRITE_BYTES:
                raise ValueError(f"Content is larger than {MAX_WRITE_BYTES} bytes.")
            return self._write_synced_file(pid, root, full, rel.replace(os.sep, "/"), data)
