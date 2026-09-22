import re
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OVERLEAF_TOKEN: str = Field(...)
    PROJECT_ID: str = Field(...)
    OVERLEAF_REPO_DIR: str = "/tmp/overleaf_repos"
    PROJECT_ID_RE: ClassVar[re.Pattern[str]] = re.compile(r"^[0-9a-f]{24}$")
    MAX_READ_BYTES: ClassVar[int] = 1_000_000
    MAX_WRITE_BYTES: ClassVar[int] = 2_000_000
    IDENTITY: ClassVar[tuple[str, str]] = ("Overleaf MCP", "overleaf-mcp@localhost")


config = Config()
