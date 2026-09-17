"""
Worker Centralized Configuration Management
Populates worker settings strictly from environment variables using Pydantic Settings.
"""

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    PROJECT_NAME: str = "InternMatch AI Worker"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    REDIS_URL: str = "redis://redis:6379/0"
    QUEUES: str = "default"

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def queue_list(self) -> List[str]:
        """Parse comma-separated queue list from configuration."""
        if not self.QUEUES:
            return ["default"]
        return [q.strip() for q in self.QUEUES.split(",") if q.strip()]


worker_settings = WorkerSettings()
