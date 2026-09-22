import unittest
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, mock_open, patch

from src.overleaf_client import OverleafClient


PROJECT_ID = "a" * 24


class TestOverleafClient(unittest.TestCase):
    @patch("src.overleaf_client.os.makedirs")
    def setUp(self, _):
        self.client = OverleafClient()

    def test_project_id_validation(self):
        with self.assertRaises(ValueError):
            self.client._resolve_project_id("project1")

        with self.assertRaises(ValueError):
            self.client._resolve_project_id("")

        self.assertEqual(self.client._resolve_project_id(PROJECT_ID), PROJECT_ID)

    @patch("src.overleaf_client.os.walk")
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

        self.assertEqual(files, ["visible/file.tex"])

    @patch("src.overleaf_client.os.path.getsize", return_value=0)
    @patch("src.overleaf_client.os.path.isfile", return_value=True)
    @patch("src.overleaf_client.open", new_callable=mock_open, read_data="test content")
    def test_read_file(self, _mock_open_file, _mock_isfile, _mock_getsize):
        with patch.object(
            self.client,
            "_sync_unlocked",
            return_value="/tmp/overleaf_repos/project1",
        ):
            content = self.client.read_file("main.tex", PROJECT_ID)
        self.assertEqual(content, "test content")

    @patch("src.overleaf_client.os.path.isfile", return_value=False)
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
            patch("src.overleaf_client.git.Repo", return_value=mock_repo),
        ):
            result = self.client.write_file("main.tex", "hello", PROJECT_ID)

        self.assertIn("pushed to Overleaf", result)
        mock_repo.git.add.assert_called_once_with("--", "main.tex")
        mock_repo.git.commit.assert_called_once()
        mock_repo.git.push.assert_called_once_with("origin", "HEAD:refs/heads/main")

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
