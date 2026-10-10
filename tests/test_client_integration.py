import base64
import os
import shutil
import unittest
from contextlib import nullcontext
from multiprocessing import Event, Process
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import Mock, mock_open, patch

import git
from filelock import FileLock

from overleaf_mcp.client import GIT_NET_TIMEOUT, OverleafClient
from overleaf_mcp.config import config
from overleaf_mcp.constants import MAX_READ_LINES

PROJECT_ID = "a" * 24


def _hold_project_lock(lock_path: str, ready: Any, release: Any) -> None:
    with FileLock(lock_path):
        ready.set()
        release.wait(10)


class TestOverleafClient(unittest.TestCase):
    @patch("overleaf_mcp.client.os.makedirs")
    def setUp(self, _):
        self._git_config_environment = {
            key: os.environ.pop(key) for key in list(os.environ) if key.startswith("GIT_CONFIG_")
        }
        os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
        os.environ["GIT_CONFIG_SYSTEM"] = os.devnull
        self.addCleanup(self._restore_git_config_environment)
        self.client = OverleafClient(default_project_id=PROJECT_ID)

    def _restore_git_config_environment(self) -> None:
        for key in list(os.environ):
            if key.startswith("GIT_CONFIG_"):
                del os.environ[key]
        os.environ.update(self._git_config_environment)

    def test_project_id_validation(self):
        with self.assertRaises(ValueError):
            self.client._resolve_project_id("project1")

        with self.assertRaises(ValueError):
            self.client._resolve_project_id("")

        self.assertEqual(self.client._resolve_project_id(PROJECT_ID), PROJECT_ID)

    def test_project_outside_allowlist_is_rejected(self):
        with (
            patch.object(config, "OVERLEAF_ALLOWED_PROJECTS", "b" * 24),
            self.assertRaisesRegex(ValueError, "not in the allowed project list"),
        ):
            self.client._resolve_project_id(PROJECT_ID)

    def test_default_allowlist_accepts_only_configured_project(self):
        other_project = "b" * 24
        with patch.object(config, "OVERLEAF_ALLOWED_PROJECTS", ""):
            self.assertEqual(self.client._resolve_project_id(PROJECT_ID), PROJECT_ID)
            with self.assertRaisesRegex(ValueError, "not in the allowed project list"):
                self.client._resolve_project_id(other_project)

    @patch("overleaf_mcp.client.shutil.which", return_value=None)
    def test_requires_git_executable(self, _mock_which):
        with self.assertRaisesRegex(RuntimeError, "Git executable not found"):
            OverleafClient(token="token", default_project_id=PROJECT_ID)

    def test_detached_head_uses_master(self):
        class DetachedGit:
            def symbolic_ref(self, *_args):
                raise git.GitCommandError("symbolic-ref", 1, stderr="missing")

            def rev_parse(self, *_args):
                return "master"

        class DetachedRepo:
            git = DetachedGit()

            @property
            def active_branch(self):
                raise TypeError

        self.assertEqual(OverleafClient._branch(cast(git.Repo, DetachedRepo())), "master")

    def test_second_process_cannot_write_while_project_is_locked(self):
        with TemporaryDirectory() as directory:
            client = OverleafClient(
                repo_dir=directory,
                token="",
                default_project_id=PROJECT_ID,
                remote_base="file:///tmp/remote",
            )
            lock_path = f"{client._project_path(PROJECT_ID)}.lock"
            ready = Event()
            release = Event()
            process = Process(target=_hold_project_lock, args=(lock_path, ready, release))
            process.start()
            try:
                self.assertTrue(ready.wait(5))
                with (
                    patch("overleaf_mcp.client.PROJECT_LOCK_TIMEOUT", 0.1),
                    self.assertRaisesRegex(RuntimeError, "Another process is using this project"),
                ):
                    client.write_file("main.tex", "blocked", PROJECT_ID)
            finally:
                release.set()
                process.join(5)
            self.assertEqual(process.exitcode, 0)

    @patch("overleaf_mcp.client.os.walk")
    def test_list_files_includes_root(self, mock_walk):
        mock_walk.return_value = [
            ("/tmp/overleaf_repos/project1", ["chapters"], ["main.tex"]),
            ("/tmp/overleaf_repos/project1/chapters", [], ["intro.tex"]),
        ]
        with patch.object(
            self.client,
            "_sync_unlocked",
            return_value="/tmp/overleaf_repos/project1",
        ):
            files = self.client.list_files(PROJECT_ID)
        self.assertEqual(files, ["chapters/intro.tex", "main.tex"])

    def test_list_files_skips_hidden_subdirs(self):
        with TemporaryDirectory() as root:
            Path(root, ".hidden").mkdir()
            Path(root, "visible").mkdir()
            Path(root, ".hidden", "secret.tex").touch()
            Path(root, "visible", ".secret.tex").touch()
            Path(root, "visible", "file.tex").touch()

            with patch.object(self.client, "_sync_unlocked", return_value=root):
                files = self.client.list_files(PROJECT_ID)

        self.assertEqual(files, [".hidden/secret.tex", "visible/.secret.tex", "visible/file.tex"])

    @patch("overleaf_mcp.client.os.path.getsize", return_value=0)
    @patch("overleaf_mcp.client.os.path.isfile", return_value=True)
    @patch("overleaf_mcp.client.open", new_callable=mock_open, read_data="test content")
    def test_read_file(self, _mock_open_file, _mock_isfile, _mock_getsize):
        with patch.object(
            self.client,
            "_sync_unlocked",
            return_value="/tmp/overleaf_repos/project1",
        ):
            content = self.client.read_file("main.tex", PROJECT_ID)
        self.assertEqual(content, "test content")

    @patch("overleaf_mcp.client.os.path.isfile", return_value=True)
    @patch(
        "overleaf_mcp.client.open",
        new_callable=mock_open,
        read_data="zero\none\ntwo\nthree\n",
    )
    def test_read_file_supports_line_offset_and_limit(self, _mock_open_file, _mock_isfile):
        with patch.object(
            self.client,
            "_sync_unlocked",
            return_value="/tmp/overleaf_repos/project1",
        ):
            content = self.client.read_file("main.tex", PROJECT_ID, offset=1, limit=2)
        self.assertEqual(content, "one\ntwo\n")

    def test_read_file_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            self.client.read_file("main.tex", PROJECT_ID, limit=0)
        with self.assertRaises(ValueError):
            self.client.read_file("main.tex", PROJECT_ID, limit=-1)
        with self.assertRaises(ValueError):
            self.client.read_file("main.tex", PROJECT_ID, limit=MAX_READ_LINES + 1)

    def test_edit_file_requires_one_unique_match(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "main.tex")
            path.write_text("alpha\nbeta\n", encoding="utf-8")
            with (
                patch.object(self.client, "_sync_unlocked", return_value=directory),
                patch.object(
                    self.client, "_write_synced_file", return_value="updated"
                ) as write_mock,
            ):
                result = self.client.edit_file("main.tex", "beta", "gamma", PROJECT_ID)
                self.assertEqual(result, "updated")
                with self.assertRaisesRegex(ValueError, "not found"):
                    self.client.edit_file("main.tex", "missing", "gamma", PROJECT_ID)
                path.write_text("beta\nbeta\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "exactly once"):
                    self.client.edit_file("main.tex", "beta", "gamma", PROJECT_ID)
                write_mock.assert_called_once()

    def test_write_file_rejects_binary_existing_file(self):
        with TemporaryDirectory() as directory:
            png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                "+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
            Path(directory, "image.png").write_bytes(png)
            with (
                patch.object(self.client, "_sync_unlocked", return_value=directory),
                self.assertRaisesRegex(ValueError, "not a UTF-8 text file"),
            ):
                self.client.write_file("image.png", "replacement", PROJECT_ID)

    @patch("overleaf_mcp.client.os.path.isfile", return_value=False)
    def test_read_file_not_found(self, _mock_isfile):
        with (
            patch.object(
                self.client,
                "_sync_unlocked",
                return_value="/tmp/overleaf_repos/project1",
            ),
            self.assertRaises(FileNotFoundError),
        ):
            self.client.read_file("nonexistent.tex", PROJECT_ID)

    def test_read_file_path_traversal(self):
        with (
            patch.object(
                self.client,
                "_sync_unlocked",
                return_value="/tmp/overleaf_repos/project1",
            ),
            self.assertRaises(ValueError),
        ):
            self.client.read_file("../../etc/passwd", PROJECT_ID)

    def test_safe_path_rejects_unsafe_paths(self):
        with TemporaryDirectory() as root:
            outside = Path(root).parent / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            Path(root, ".git").mkdir()

            with self.assertRaises(ValueError):
                self.client._safe_path(root, "../outside.txt")
            with self.assertRaises(ValueError):
                self.client._safe_path(root, str(outside))
            with self.assertRaises(ValueError):
                self.client._safe_path(root, ".git/config")
            with self.assertRaises(ValueError):
                self.client._safe_path(root, ".GIT/config")
            with self.assertRaises(ValueError):
                self.client._safe_path(root, "bad\x00name")

            symlink = Path(root, "link")
            symlink.symlink_to(outside)
            with self.assertRaises(ValueError):
                self.client._safe_path(root, "link")

    def test_write_file(self):
        mock_repo = Mock()
        mock_repo.git.custom_environment.return_value = nullcontext()
        mock_repo.git.status.return_value = " M main.tex"
        mock_repo.active_branch.name = "main"
        mock_repo.head.commit.hexsha = "a" * 40
        with (
            patch.object(
                self.client,
                "_sync_unlocked",
                return_value="/tmp/overleaf_repos/project1",
            ),
            patch.object(self.client, "_atomic_write"),
            patch("overleaf_mcp.client.git.Repo", return_value=mock_repo),
        ):
            result = self.client.write_file("main.tex", "hello", PROJECT_ID)

        self.assertIn("pushed to Overleaf", result)
        mock_repo.git.add.assert_called_once_with("--", "main.tex")
        mock_repo.git.commit.assert_called_once()
        mock_repo.git.push.assert_called_once_with(
            "origin", "HEAD:refs/heads/main", kill_after_timeout=GIT_NET_TIMEOUT
        )

    def test_push_error_confirms_remote_commit(self):
        token = "token-for-test"
        mock_repo = Mock()
        mock_repo.git.custom_environment.return_value = nullcontext()
        mock_repo.git.status.return_value = " M main.tex"
        mock_repo.git.push.side_effect = git.GitCommandError("push", 124, stderr=f"timeout {token}")
        mock_repo.git.rev_list.return_value = "0\n"
        mock_repo.active_branch.name = "main"
        mock_repo.head.commit.hexsha = "a" * 40
        client = OverleafClient(
            repo_dir="/tmp/overleaf-test",
            token=token,
            default_project_id=PROJECT_ID,
            remote_base="file:///tmp/remote",
        )

        with (
            patch.object(client, "_sync_unlocked", return_value="/tmp/project"),
            patch.object(client, "_atomic_write"),
            patch("overleaf_mcp.client.git.Repo", return_value=mock_repo),
        ):
            result = client.write_file("main.tex", "hello", PROJECT_ID)

        self.assertIn("confirmed after error", result)
        self.assertNotIn(token, result)
        self.assertNotIn(base64.b64encode(f"git:{token}".encode()).decode(), result)
        mock_repo.git.reset.assert_not_called()

    def test_push_error_with_unknown_result_does_not_reset(self):
        mock_repo = Mock()
        mock_repo.git.custom_environment.return_value = nullcontext()
        mock_repo.git.status.return_value = " M main.tex"
        mock_repo.git.push.side_effect = git.GitCommandError("push", 124, stderr="timeout")
        mock_repo.git.fetch.side_effect = git.GitCommandError("fetch", 1, stderr="offline")
        mock_repo.active_branch.name = "main"
        mock_repo.head.commit.hexsha = "a" * 40
        with (
            patch.object(self.client, "_sync_unlocked", return_value="/tmp/project"),
            patch.object(self.client, "_atomic_write"),
            patch("overleaf_mcp.client.git.Repo", return_value=mock_repo),
            self.assertRaisesRegex(RuntimeError, "Push result unknown"),
        ):
            self.client.write_file("main.tex", "hello", PROJECT_ID)
        mock_repo.git.reset.assert_not_called()

    def test_rejected_push_discards_local_commit(self):
        mock_repo = Mock()
        mock_repo.git.custom_environment.return_value = nullcontext()
        mock_repo.git.status.return_value = " M main.tex"
        mock_repo.git.push.side_effect = git.GitCommandError(
            "push", 1, stderr="non-fast-forward rejected"
        )
        mock_repo.git.rev_list.return_value = "1\n"
        mock_repo.active_branch.name = "main"
        mock_repo.head.commit.hexsha = "a" * 40
        with (
            patch.object(self.client, "_sync_unlocked", return_value="/tmp/project"),
            patch.object(self.client, "_atomic_write"),
            patch("overleaf_mcp.client.git.Repo", return_value=mock_repo),
            self.assertRaisesRegex(RuntimeError, "Push rejected"),
        ):
            self.client.write_file("main.tex", "hello", PROJECT_ID)
        mock_repo.git.reset.assert_called_once_with("--hard", "origin/main")

    def test_rejected_push_against_bare_repo_resets_to_remote(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            remote_root = root / "remote"
            remote_root.mkdir()
            remote_path = remote_root / PROJECT_ID
            bare = git.Repo.init(remote_path, bare=True)

            seed_path = root / "seed"
            seed = git.Repo.init(seed_path, initial_branch="main")
            Path(seed_path, "main.tex").write_text("initial\n", encoding="utf-8")
            actor = git.Actor("Test User", "test@example.com")
            seed.index.add(["main.tex"])
            seed.index.commit("initial", author=actor, committer=actor)
            seed.create_remote("origin", remote_path.as_uri())
            seed.git.push("origin", "main")
            bare.git.symbolic_ref("HEAD", "refs/heads/main")

            client = OverleafClient(
                repo_dir=root / "cache",
                token="",
                default_project_id=PROJECT_ID,
                remote_base=remote_root.as_uri(),
            )
            client.ensure_repo()

            other_path = root / "other"
            other = git.Repo.clone_from(remote_path.as_uri(), other_path, branch="main")

            original_sync = client._sync_unlocked
            remote_changed = False

            def sync_then_remote_change(project_id: str, force: bool) -> str:
                nonlocal remote_changed
                path = original_sync(project_id, force)
                if not remote_changed:
                    Path(other_path, "main.tex").write_text("remote change\n", encoding="utf-8")
                    other.index.add(["main.tex"])
                    other.index.commit("remote change", author=actor, committer=actor)
                    other.git.push("origin", "main")
                    remote_changed = True
                return path

            with (
                patch.object(client, "_sync_unlocked", side_effect=sync_then_remote_change),
                self.assertRaisesRegex(RuntimeError, "Push rejected"),
            ):
                client.write_file("main.tex", "local change\n", PROJECT_ID)

            self.assertEqual(client.read_file("main.tex", PROJECT_ID), "remote change\n")

    def test_corrupt_cache_is_recloned(self):
        with TemporaryDirectory() as directory:
            client = self._create_bare_client(Path(directory), "token-for-test")
            cache_path = Path(client._project_path(PROJECT_ID))
            shutil.rmtree(cache_path / ".git")
            (cache_path / ".git").mkdir()

            client.ensure_repo(PROJECT_ID)

            self.assertEqual(client.read_file("main.tex", PROJECT_ID), "initial\n")

    def test_failed_push_forces_next_read_to_sync_remote(self):
        token = "token-for-test"
        with TemporaryDirectory() as directory:
            client = self._create_bare_client(Path(directory), token)
            original_execute = git.cmd.Git.execute

            def auth_failure(repo_git, *args, **kwargs):
                command = args[0] if args else []
                if "push" in command:
                    raise git.GitCommandError("push", 128, stderr=f"auth failed {token}")
                return original_execute(repo_git, *args, **kwargs)

            with (
                patch.object(git.cmd.Git, "execute", new=auth_failure),
                self.assertRaisesRegex(RuntimeError, "discarded"),
            ):
                client.write_file("main.tex", "never landed\n", PROJECT_ID)

            self.assertEqual(client.read_file("main.tex", PROJECT_ID), "initial\n")

    def _create_bare_client(self, root: Path, token: str) -> OverleafClient:
        remote_root = root / "remote"
        remote_root.mkdir()
        remote_path = remote_root / PROJECT_ID
        bare = git.Repo.init(remote_path, bare=True)

        seed_path = root / "seed"
        seed = git.Repo.init(seed_path, initial_branch="main")
        Path(seed_path, "main.tex").write_text("initial\n", encoding="utf-8")
        actor = git.Actor("Test User", "test@example.com")
        seed.index.add(["main.tex"])
        seed.index.commit("initial", author=actor, committer=actor)
        seed.create_remote("origin", remote_path.as_uri())
        seed.git.push("origin", "main")
        bare.git.symbolic_ref("HEAD", "refs/heads/main")

        client = OverleafClient(
            repo_dir=root / "cache",
            token=token,
            default_project_id=PROJECT_ID,
            remote_base=remote_root.as_uri(),
        )
        client.ensure_repo()
        return client

    def test_landed_push_is_confirmed_against_bare_repo(self):
        token = "token-for-test"
        with TemporaryDirectory() as directory:
            client = self._create_bare_client(Path(directory), token)
            original_execute = git.cmd.Git.execute

            def push_then_raise(repo_git, *args, **kwargs):
                result = original_execute(repo_git, *args, **kwargs)
                command = args[0] if args else []
                if "push" in command:
                    raise git.GitCommandError("push", 124, stderr=f"timeout {token}")
                return result

            with patch.object(git.cmd.Git, "execute", new=push_then_raise):
                result = client.write_file("main.tex", "landed\n", PROJECT_ID)

        encoded = base64.b64encode(f"git:{token}".encode()).decode()
        self.assertIn("confirmed after error", result)
        self.assertNotIn(token, result)
        self.assertNotIn(encoded, result)

    def test_unknown_push_result_is_reported_against_bare_repo(self):
        token = "token-for-test"
        with TemporaryDirectory() as directory:
            client = self._create_bare_client(Path(directory), token)
            original_execute = git.cmd.Git.execute
            pushed = False

            def execute_then_raise(repo_git, *args, **kwargs):
                nonlocal pushed
                command = args[0] if args else []
                if pushed and "fetch" in command:
                    raise git.GitCommandError("fetch", 1, stderr=f"offline {token}")
                result = original_execute(repo_git, *args, **kwargs)
                if "push" in command:
                    pushed = True
                    raise git.GitCommandError("push", 124, stderr=f"timeout {token}")
                return result

            with (
                patch.object(git.cmd.Git, "execute", new=execute_then_raise),
                self.assertRaisesRegex(RuntimeError, "Push result unknown") as raised,
            ):
                client.write_file("main.tex", "unknown\n", PROJECT_ID)

        message = str(raised.exception)
        encoded = base64.b64encode(f"git:{token}".encode()).decode()
        self.assertNotIn(token, message)
        self.assertNotIn(encoded, message)

    def test_scrubbing_hides_token_and_encoded_token(self):
        token = "token-for-test"
        encoded = base64.b64encode(f"git:{token}".encode()).decode()
        client = OverleafClient(token=token, default_project_id=PROJECT_ID)
        with self.assertRaises(RuntimeError) as raised, client._scrubbed():
            raise git.GitCommandError("push", 1, stderr=f"{token} {encoded}")

        self.assertNotIn(token, str(raised.exception))
        self.assertNotIn(encoded, str(raised.exception))

    def test_write_file_path_traversal(self):
        with (
            patch.object(
                self.client,
                "_sync_unlocked",
                return_value="/tmp/overleaf_repos/project1",
            ),
            self.assertRaises(ValueError),
        ):
            self.client.write_file("../../etc/pwned", "evil", PROJECT_ID)


if __name__ == "__main__":
    unittest.main()
