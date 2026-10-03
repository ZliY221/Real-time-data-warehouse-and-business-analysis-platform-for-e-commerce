from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse


@dataclass(frozen=True)
class ApiSettings:
    clickhouse_url: str = "http://localhost:8123"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "ecommerce"
    clickhouse_timeout_seconds: float = 3.0

    @classmethod
    def from_env(cls) -> "ApiSettings":
        timeout_text = os.getenv("CLICKHOUSE_TIMEOUT_SECONDS", "3")
        try:
            timeout = float(timeout_text)
        except ValueError as error:
            raise ValueError("CLICKHOUSE_TIMEOUT_SECONDS must be a number") from error

        settings = cls(
            clickhouse_url=os.getenv("CLICKHOUSE_HTTP_URL", "http://localhost:8123"),
            clickhouse_user=os.getenv("CLICKHOUSE_USER", "default"),
            clickhouse_password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            clickhouse_database=os.getenv("CLICKHOUSE_DATABASE", "ecommerce"),
            clickhouse_timeout_seconds=timeout,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        parsed_url = urlparse(self.clickhouse_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("CLICKHOUSE_HTTP_URL must be an absolute http or https URL")
        if parsed_url.username or parsed_url.password:
            raise ValueError("Put ClickHouse credentials in environment variables, not in the URL")
        if not self.clickhouse_user.strip():
            raise ValueError("CLICKHOUSE_USER must not be blank")
        if not self.clickhouse_database.strip():
            raise ValueError("CLICKHOUSE_DATABASE must not be blank")
        if self.clickhouse_timeout_seconds <= 0:
            raise ValueError("CLICKHOUSE_TIMEOUT_SECONDS must be greater than zero")

