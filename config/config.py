import re
from pathlib import Path
from typing import ClassVar

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    OVERLEAF_TOKEN: SecretStr = Field(...)
    PROJECT_ID: str = Field(...)
    OVERLEAF_REPO_DIR: Path = Path.home() / ".cache" / "overleaf-mcp"
    PROJECT_ID_RE: ClassVar[re.Pattern[str]] = re.compile(r"^[0-9a-f]{24}$")
    MAX_READ_BYTES: ClassVar[int] = 100_000
    MAX_READ_LINES: ClassVar[int] = 10_000
    MAX_WRITE_BYTES: ClassVar[int] = 2_000_000
    IDENTITY: ClassVar[tuple[str, str]] = ("Overleaf MCP", "overleaf-mcp@localhost")


config = Config()
