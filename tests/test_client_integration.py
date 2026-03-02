import os
import unittest
from unittest.mock import MagicMock, patch
from src.overleaf_client import OverleafClient

class TestOverleafClient(unittest.TestCase):
    def setUp(self):
        # Prevent it from actually creating dirs, etc.
        with patch('os.makedirs'):
            self.client = OverleafClient()

    @patch('git.Repo.clone_from')
    @patch('os.path.exists')
    @patch('os.walk')
    def test_fetch_project_files_mock(self, mock_walk, mock_exists, mock_clone):
        # Mock os.path.exists to simulate repo not existing initially
        mock_exists.side_effect = lambda path: ".git" in path if "tmp" in path else True
        
        # Mock os.walk
        mock_walk.return_value = [
            ('/tmp/overleaf_repos/project1', [], ['main.tex', 'style.cls']),
        ]
        
        # Use our mocked client (no network)
        with patch.object(OverleafClient, 'ensure_repo', return_value='/tmp/overleaf_repos/project1'):
            files = self.client.fetch_project_files("project1")
            self.assertEqual(files, ["main.tex", "style.cls"])

    @patch('src.overleaf_client.open', new_callable=unittest.mock.mock_open, read_data="test content")
    @patch('os.path.exists', return_value=True)
    def test_read_file_mock(self, mock_exists, mock_file):
        with patch.object(OverleafClient, 'ensure_repo', return_value='/tmp/overleaf_repos/project1'):
            content = self.client.read_file("project1", "main.tex")
            self.assertEqual(content, "test content")

if __name__ == '__main__':
    unittest.main()
