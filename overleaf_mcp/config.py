import os
import re
from pathlib import Path
from typing import ClassVar

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_ENV_FILE = (
    Path(os.environ["OVERLEAF_ENV_FILE"])
    if os.environ.get("OVERLEAF_ENV_FILE")
    else (_PACKAGE_ENV_FILE if _PACKAGE_ENV_FILE.exists() else None)
)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    OVERLEAF_TOKEN: SecretStr = Field(...)
    PROJECT_ID: str = Field(...)
    OVERLEAF_ALLOWED_PROJECTS: str = ""
    OVERLEAF_REPO_DIR: Path = Path.home() / ".cache" / "overleaf-mcp"
    PROJECT_ID_RE: ClassVar[re.Pattern[str]] = re.compile(r"^[0-9a-f]{24}$")


config = Config()
