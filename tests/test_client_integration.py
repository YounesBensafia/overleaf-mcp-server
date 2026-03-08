import unittest
from unittest.mock import Mock, mock_open, patch

from src.overleaf_client import OverleafClient


class TestOverleafClient(unittest.TestCase):
    @patch("src.overleaf_client.os.makedirs")
    def setUp(self, _):
        self.client = OverleafClient()

    @patch("src.overleaf_client.os.walk")
    def test_list_files(self, mock_walk):
        mock_walk.return_value = [
            ("/tmp/overleaf_repos/project1", ["chapters"], ["main.tex"]),
            ("/tmp/overleaf_repos/project1/chapters", [], ["intro.tex"]),
        ]
        with patch.object(self.client, "ensure_repo", return_value="/tmp/overleaf_repos/project1"):
            files = self.client.list_files("project1")
        self.assertEqual(files, ["main.tex", "chapters/intro.tex"])

    @patch("src.overleaf_client.os.path.exists", return_value=True)
    @patch("src.overleaf_client.open", new_callable=mock_open, read_data="test content")
    def test_read_file(self, _mock_open_file, _mock_exists):
        with patch.object(self.client, "ensure_repo", return_value="/tmp/overleaf_repos/project1"):
            content = self.client.read_file("main.tex", "project1")
        self.assertEqual(content, "test content")

    @patch("src.overleaf_client.os.path.exists", return_value=True)
    @patch("src.overleaf_client.open", new_callable=mock_open)
    def test_write_file(self, _mock_open_file, _mock_exists):
        mock_repo = Mock()
        with patch.object(self.client, "ensure_repo", return_value="/tmp/overleaf_repos/project1"):
            with patch("src.overleaf_client.git.Repo", return_value=mock_repo):
                result = self.client.write_file("main.tex", "hello", "project1")

        self.assertIn("pushed to Overleaf", result)
        mock_repo.index.add.assert_called_once_with(["main.tex"])
        mock_repo.index.commit.assert_called_once()
        mock_repo.remotes.origin.push.assert_called_once()


if __name__ == "__main__":
    unittest.main()
