import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError

from overleaf_mcp.config import Config


class TestConfig(unittest.TestCase):
    def test_loads_dotenv_values_and_ignores_extra_keys(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory, ".env")
            env_file.write_text(
                "OVERLEAF_TOKEN=file-token\n"
                "PROJECT_ID=0123456789abcdef01234567\n"
                "OVERLEAF_REPO_DIR=/var/lib/overleaf\n"
                "UNUSED_SETTING=ignored\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Config(_env_file=env_file)

        self.assertEqual(settings.OVERLEAF_TOKEN.get_secret_value(), "file-token")
        self.assertEqual(settings.PROJECT_ID, "0123456789abcdef01234567")
        self.assertEqual(str(settings.OVERLEAF_REPO_DIR), "/var/lib/overleaf")

    def test_environment_overrides_dotenv_values(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory, ".env")
            env_file.write_text(
                "OVERLEAF_TOKEN=file-token\nPROJECT_ID=0123456789abcdef01234567\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "OVERLEAF_TOKEN": "environment-token",
                    "PROJECT_ID": "fedcba9876543210fedcba98",
                },
                clear=True,
            ):
                settings = Config(_env_file=env_file)

        self.assertEqual(settings.OVERLEAF_TOKEN.get_secret_value(), "environment-token")
        self.assertEqual(settings.PROJECT_ID, "fedcba9876543210fedcba98")

    def test_secret_token_is_hidden_from_repr_and_str(self):
        settings = Config(
            OVERLEAF_TOKEN="olp_test",
            PROJECT_ID="0123456789abcdef01234567",
        )

        self.assertNotIn("olp_test", repr(settings))
        self.assertNotIn("olp_test", str(settings))

    def test_requires_token_and_project_id(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValidationError):
            Config(_env_file=None)


if __name__ == "__main__":
    unittest.main()
