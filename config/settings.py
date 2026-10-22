import os
import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class RepoConfig(BaseModel):
    repo: str
    enabled: bool = True
    labels: List[str] = ["good first issue", "help wanted"]
    priority: int = 1
    notes: Optional[str] = ""

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # GitHub
    GITHUB_TOKEN: str = "placeholder_token"
    GITHUB_USERNAME: str = "placeholder_user"

    # Gemini
    GEMINI_API_KEY: str = "placeholder_gemini"
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Grok / xAI
    GROK_API_KEY: str = "placeholder_grok"
    GROK_MODEL: str = "grok-2-latest"
    GROK_BASE_URL: str = "https://api.x.ai/v1"

    # Time Window (e.g., "12:00" to "14:00")
    WORK_WINDOW_START: str = "12:00"
    WORK_WINDOW_END: str = "14:00"
    TIMEZONE: str = "Asia/Kolkata"

    # Safety
    DRY_RUN: bool = True
    REQUIRE_APPROVAL: bool = True

    # Storage paths
    WORKSPACES_DIR: str = str(BASE_DIR / "cloned_repos")
    REPOS_CONFIG_PATH: str = str(BASE_DIR / "config" / "repos.json")
    STATE_FILE_PATH: str = str(BASE_DIR / "config" / "agent_state.json")

def load_repos_config(file_path: Optional[str] = None) -> List[RepoConfig]:
    path = Path(file_path or Settings().REPOS_CONFIG_PATH)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return [RepoConfig(**item) for item in data]

def save_repos_config(repos: List[RepoConfig], file_path: Optional[str] = None) -> None:
    path = Path(file_path or Settings().REPOS_CONFIG_PATH)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in repos], f, indent=2)

settings = Settings()
